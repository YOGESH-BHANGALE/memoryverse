"""
Backfill the ``date`` metadata field on entities stored before the range fallback.

Why this exists
---------------
The extractor often returns a whole range in a single-date field — a
certification dated "Jul 2025 - Oct 2025", an achievement dated "2025 - 2026".
The categorizer used to pass those straight to ``normalise_date``, which only
understands a single date, so it returned None and the entity was stored
undated. On a real resume that left 95 of 103 entities missing from the dated
timeline: certifications, projects and achievements all silently collapsed into
an "Undated" bucket even though the source document stated their dates.

``app.core.ingestion.categorizer.entity_date`` now tries ``date_range_start`` as
a fallback for every date-ish field. This script applies that same function to
entities already in ChromaDB, reading the dates out of the ``data_json`` blob
that was persisted alongside them — so nothing is re-extracted, re-embedded, or
sent to an LLM.

Only the ``date`` key changes. Chroma's ``update`` replaces a record's metadata
wholesale rather than merging, so each row is read, mutated and written back
intact; writing just {"date": ...} would erase title, tags and relations.

Usage
-----
    # from the backend/ directory, with the project venv active
    python scripts/backfill_dates.py                     # dry run, all users
    python scripts/backfill_dates.py --user <user_id>    # dry run, one user
    python scripts/backfill_dates.py --apply             # write the dates

Safe to re-run: rows whose date already matches are left alone.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# Allow running as `python scripts/backfill_dates.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.core.ingestion.categorizer import entity_date
from app.core.vectordb.client import COLLECTIONS, ChromaClient
from app.models.schemas import EntityCategory

BATCH = 100


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the recomputed dates (default is a dry run)")
    ap.add_argument("--user", default=None,
                    help="restrict to a single user_id (default: every user)")
    args = ap.parse_args()

    settings = get_settings()
    print(f"ChromaDB path : {settings.chroma_path}")
    print(f"user filter   : {args.user or '(all users)'}")
    print(f"mode          : {'APPLY' if args.apply else 'DRY RUN'}\n")

    chroma = ChromaClient()
    categories = {c.value: c for c in EntityCategory}
    stats: Counter[str] = Counter()

    for col_short in COLLECTIONS:
        if col_short == "raw_chunks":
            continue

        col = chroma.get_collection(col_short)
        where = {"user_id": args.user} if args.user else None
        payload = col.get(where=where, include=["metadatas"], limit=100_000)
        ids = payload.get("ids") or []
        metas = payload.get("metadatas") or []

        pending_ids: list[str] = []
        pending_metas: list[dict] = []
        unchanged = 0

        for row_id, meta in zip(ids, metas):
            meta = dict(meta or {})
            category = categories.get(meta.get("category", ""))
            if category is None:
                continue
            try:
                data = json.loads(meta.get("data_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                data = {}
            if not isinstance(data, dict):
                continue

            resolved = entity_date(category, data)
            current = meta.get("date") or None
            if resolved == current:
                unchanged += 1
                continue
            # A resolvable date is an improvement; an unresolvable one is not a
            # reason to erase a date that some earlier ingest got right.
            if not resolved:
                unchanged += 1
                continue

            title = meta.get("title", "")[:44]
            print(f"   {str(current or '(none)'):9} -> {resolved}   {title}")
            meta["date"] = resolved
            pending_ids.append(row_id)
            pending_metas.append(meta)

        print(f"-- {col_short}: {len(ids)} row(s), "
              f"{len(pending_ids)} to update, {unchanged} unchanged")
        stats["scanned"] += len(ids)
        stats["updated"] += len(pending_ids)

        if args.apply and pending_ids:
            for start in range(0, len(pending_ids), BATCH):
                col.update(
                    ids=pending_ids[start:start + BATCH],
                    metadatas=pending_metas[start:start + BATCH],
                )

    print(f"\nScanned {stats['scanned']} row(s); "
          f"{stats['updated']} date(s) {'written' if args.apply else 'would change'}.")
    if not args.apply:
        print("DRY RUN - nothing written. Re-run with --apply.")
    elif stats["updated"]:
        print("\nRebuild the graph so temporal evidence picks up the new dates:")
        print("  POST /api/relations/rebuild/{user_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
