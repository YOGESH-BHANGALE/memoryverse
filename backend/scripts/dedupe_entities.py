"""
One-off migration: collapse duplicate entities onto deterministic IDs.

Why this exists
---------------
Categorizer used to mint a fresh ``uuid4()`` for every extracted entity, so each
re-upload of the same resume created a brand-new row rather than overwriting the
old one. A single corpus ended up holding "MemoryVerse AI" three times, eleven
internship rows for three real internships, and four copies of the same degree.
That inflates the dashboard counts, triples the timeline, and makes the knowledge
graph show the same edge repeatedly.

``app.core.ingestion.categorizer.stable_entity_id`` fixes this going forward
(the ID is a sha1 of user|category|normalised-title, so re-ingesting upserts onto
the same row). This script repairs rows written *before* that change.

For each group of rows that share a canonical ID:
  * the richest record wins (most populated ``data_json``, then longest document)
  * it is re-upserted under its canonical ID, reusing its existing embedding —
    nothing is re-embedded, so no Groq/HuggingFace calls are made
  * the remaining rows are deleted, after being written to a JSON backup file

Titles are compared case-insensitively with whitespace collapsed and trailing
punctuation stripped, so "Traveo", "traveo" and "Traveo." merge. Records whose
titles genuinely differ ("Intern @ Ethara AI" vs "LLM Post-Training Intern @
Ethara AI") are *not* merged — they are only reported, since deciding they are
the same thing is a judgement call, not a mechanical one.

Usage
-----
    # from the backend/ directory, with the project venv active
    python scripts/dedupe_entities.py                        # dry run, all users
    python scripts/dedupe_entities.py --user <user_id>       # dry run, one user
    python scripts/dedupe_entities.py --apply                # perform the merge
    python scripts/dedupe_entities.py --apply --no-backup    # skip the JSON backup

Safe to re-run: a corpus that is already deduplicated reports "nothing to do".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Allow running as `python scripts/dedupe_entities.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.core.ingestion.categorizer import stable_entity_id
from app.core.vectordb.client import COLLECTIONS, ChromaClient
from app.models.schemas import EntityCategory

BATCH = 100

# Words too generic to make two titles "the same thing".
_TITLE_NOISE = {"the", "and", "for", "with", "intern", "internship", "engineer",
                "engineering", "developer", "remote", "certificate", "certification",
                "course", "project", "bachelor", "degree"}


def _richness(meta: dict, document: str) -> tuple[int, int]:
    """Sort key for picking the survivor: most extracted data, then most text."""
    raw = meta.get("data_json") or "{}"
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        data = {}
    populated = sum(1 for v in (data or {}).values() if v not in (None, "", [], {}))
    return (populated, len(document or ""))


def _canonical_id(meta: dict, category: EntityCategory) -> str | None:
    title = (meta.get("title") or "").strip()
    user_id = (meta.get("user_id") or "").strip()
    if not title or not user_id:
        return None
    return stable_entity_id(user_id, category, title)


def _near_duplicate_report(
    col_short: str, ids: list[str], metas: list[dict]
) -> list[str]:
    """
    Flag titles that look like the same thing but are not mechanically equal.

    "Intern @ Ethara AI Remote" and "LLM Post-Training Intern @ Ethara AI" are
    almost certainly one internship, but merging them means choosing which title
    is the real one — a judgement call, so these are only reported. The test is
    a strict token-subset: every meaningful word of one title appears in the
    other. That is deliberately conservative; loose overlap flagged unrelated
    skills like "Machine Learning" and "Learning Rate Schedules".
    """
    tokens: list[tuple[str, str, set[str]]] = []
    for idx, _ in enumerate(ids):
        meta = metas[idx] or {}
        title = (meta.get("title") or "").strip()
        if not title:
            continue
        words = {
            w for w in re.split(r"[^a-z0-9+#]+", title.lower())
            if len(w) >= 3 and w not in _TITLE_NOISE
        }
        if words:
            tokens.append((meta.get("user_id", ""), title, words))

    out: list[str] = []
    # Duplicate rows would otherwise report the same title pair once per copy.
    seen_pairs: set[frozenset[str]] = set()
    for i in range(len(tokens)):
        u_a, title_a, words_a = tokens[i]
        for j in range(i + 1, len(tokens)):
            u_b, title_b, words_b = tokens[j]
            if u_a != u_b or words_a == words_b:
                continue
            if not (words_a <= words_b or words_b <= words_a):
                continue
            pair = frozenset((title_a.lower(), title_b.lower()))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            out.append(f"{col_short}: {title_a[:45]}  ~=  {title_b[:45]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="perform the merge (default is a dry run)")
    ap.add_argument("--user", default=None,
                    help="restrict to a single user_id (default: every user)")
    ap.add_argument("--no-backup", action="store_true",
                    help="do not write deleted rows to a JSON backup file")
    args = ap.parse_args()

    settings = get_settings()
    print(f"ChromaDB path : {settings.chroma_path}")
    print(f"user filter   : {args.user or '(all users)'}")
    print(f"mode          : {'APPLY' if args.apply else 'DRY RUN'}\n")

    chroma = ChromaClient()
    categories = {c.value: c for c in EntityCategory}

    total_rows = 0
    total_removed = 0
    total_relocated = 0
    backup: list[dict] = []
    near_duplicates: list[str] = []

    for col_short in COLLECTIONS:
        if col_short == "raw_chunks":
            continue

        col = chroma.get_collection(col_short)
        where = {"user_id": args.user} if args.user else None
        payload = col.get(
            where=where,
            include=["documents", "metadatas", "embeddings"],
            limit=100_000,
        )
        ids = payload.get("ids") or []
        docs = payload.get("documents") or []
        metas = payload.get("metadatas") or []
        embs = payload.get("embeddings")
        embs = list(embs) if embs is not None else None
        total_rows += len(ids)

        # Group rows by the ID they *should* have.
        groups: dict[str, list[int]] = defaultdict(list)
        unkeyed = 0
        for idx, row_id in enumerate(ids):
            meta = metas[idx] or {}
            category = categories.get(meta.get("category", ""))
            if category is None:
                unkeyed += 1
                continue
            canonical = _canonical_id(meta, category)
            if canonical is None:
                unkeyed += 1
                continue
            groups[canonical].append(idx)

        has_embeddings = embs is not None and len(embs) == len(ids)
        dupes = {k: v for k, v in groups.items() if len(v) > 1}
        misfiled = {
            k: v for k, v in groups.items()
            if len(v) == 1 and ids[v[0]] != k
        }

        print(f"-- {col_short}: {len(ids)} row(s)"
              + (f", {unkeyed} unkeyable" if unkeyed else ""))

        near_duplicates.extend(_near_duplicate_report(col_short, ids, metas))

        if not dupes and not misfiled:
            print("   nothing to do")
            continue

        # Collected first, flushed in batches at the end of the collection, so a
        # row is never deleted before its replacement is safely written.
        keep_ids: list[str] = []
        keep_rows: list[int] = []
        delete_ids: set[str] = set()

        for canonical, indices in sorted(dupes.items(), key=lambda kv: -len(kv[1])):
            # Richest record wins; ties break toward a row already sitting on the
            # canonical ID, which keeps the write a no-op instead of a move.
            indices.sort(
                key=lambda i: (_richness(metas[i] or {}, docs[i] or ""),
                               ids[i] == canonical),
                reverse=True,
            )
            keep, drop = indices[0], indices[1:]
            title = (metas[keep] or {}).get("title", "(untitled)")
            print(f"   {len(indices)}x  {title[:60]}")
            print(f"        keep {ids[keep][:12]}...  drop {[ids[i][:8] for i in drop]}")

            keep_ids.append(canonical)
            keep_rows.append(keep)
            for i in drop:
                delete_ids.add(ids[i])
                backup.append({
                    "collection": col_short,
                    "id": ids[i],
                    "document": docs[i],
                    "metadata": metas[i],
                })
            if ids[keep] != canonical:
                delete_ids.add(ids[keep])
            total_removed += len(drop)

        for canonical, (idx,) in misfiled.items():
            # Unique record, but sitting under a legacy uuid4 ID. Relocating it
            # onto the canonical ID is what makes the next re-upload idempotent.
            print(f"   re-key {ids[idx][:12]}... -> {canonical[:12]}...  "
                  f"{(metas[idx] or {}).get('title', '')[:45]}")
            keep_ids.append(canonical)
            keep_rows.append(idx)
            delete_ids.add(ids[idx])
            total_relocated += 1

        if not args.apply:
            continue

        for start in range(0, len(keep_ids), BATCH):
            rows = keep_rows[start:start + BATCH]
            kwargs = {
                "ids": keep_ids[start:start + BATCH],
                "documents": [docs[i] for i in rows],
                "metadatas": [metas[i] or {} for i in rows],
            }
            if has_embeddings:
                kwargs["embeddings"] = [embs[i] for i in rows]
            col.upsert(**kwargs)

        # A survivor's canonical ID can coincide with a dropped row's legacy ID
        # (one of the duplicates was already correctly keyed). Subtracting the
        # written IDs stops the delete from undoing the upsert above.
        stale = sorted(delete_ids - set(keep_ids))
        for start in range(0, len(stale), BATCH):
            col.delete(ids=stale[start:start + BATCH])

    print(f"\nScanned {total_rows} row(s) across {len(COLLECTIONS) - 1} collection(s).")

    if near_duplicates:
        print(f"\n{len(near_duplicates)} near-duplicate title pair(s) - NOT merged, "
              f"review by hand:")
        for line in near_duplicates[:25]:
            print(f"   {line}")
        if len(near_duplicates) > 25:
            print(f"   ... and {len(near_duplicates) - 25} more")

    if not args.apply:
        print("\nDRY RUN - nothing written. Re-run with --apply to merge.")
        return 0

    print(f"Merged away {total_removed} duplicate row(s); "
          f"re-keyed {total_relocated} unique row(s).")

    if backup and not args.no_backup:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path("backups") / f"deduped_entities_{stamp}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(backup, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Backup of {len(backup)} deleted row(s): {path}")

    if total_removed or total_relocated:
        print("\nRebuild the knowledge graph so relations point at the surviving IDs:")
        print("  POST /api/relations/rebuild/{user_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
