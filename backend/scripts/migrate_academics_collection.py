"""
One-off migration: move records stranded in the legacy "<prefix>_academicss"
collection into the correct "<prefix>_academics" collection.

Why this exists
---------------
Collection names were derived with a naive f"{category.value}s". Every
EntityCategory value is singular ("skill" -> "skills") except ACADEMICS, whose
value is already plural — so academic entities were written to
"memoryverse_academicss" while every read path (timeline, identity, search,
relations) only ever scanned the names listed in COLLECTIONS. The academics
records were therefore invisible to the whole application.

The code defect is fixed in app/core/vectordb/client.py
(collection_for_category); this script relocates the data that was written
before the fix. Existing embeddings are copied as-is, so nothing is re-embedded
and no Groq/HuggingFace calls are made.

Usage
-----
    # from the backend/ directory, with the project venv active
    python scripts/migrate_academics_collection.py            # dry run
    python scripts/migrate_academics_collection.py --apply     # perform the copy
    python scripts/migrate_academics_collection.py --apply --delete-legacy

Safe to re-run: records are upserted by their existing IDs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python scripts/migrate_academics_collection.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings

LEGACY_SUFFIX = "academicss"
TARGET_SUFFIX = "academics"

BATCH = 100


def _get(client, name):
    """Return a collection or None if it does not exist."""
    try:
        return client.get_collection(name=name)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="perform the migration (default is a dry run)")
    ap.add_argument("--delete-legacy", action="store_true",
                    help="drop the legacy collection after a verified copy")
    args = ap.parse_args()

    settings = get_settings()
    prefix = settings.chroma_collection_prefix
    legacy_name = f"{prefix}_{LEGACY_SUFFIX}"
    target_name = f"{prefix}_{TARGET_SUFFIX}"

    print(f"ChromaDB path : {settings.chroma_path}")
    print(f"legacy        : {legacy_name}")
    print(f"target        : {target_name}")
    print(f"mode          : {'APPLY' if args.apply else 'DRY RUN'}\n")

    client = chromadb.PersistentClient(
        path=str(settings.chroma_path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )

    legacy = _get(client, legacy_name)
    if legacy is None:
        print(f"Nothing to do: '{legacy_name}' does not exist "
              f"(already migrated, or this DB predates the bug).")
        return 0

    legacy_count = legacy.count()
    print(f"Found {legacy_count} record(s) in the legacy collection.")
    if legacy_count == 0:
        print("Legacy collection is empty — nothing to migrate.")
        return 0

    payload = legacy.get(include=["documents", "metadatas", "embeddings"])
    ids = payload.get("ids") or []
    docs = payload.get("documents") or []
    metas = payload.get("metadatas") or []
    embs = payload.get("embeddings")
    embs = list(embs) if embs is not None else None

    # Show what will move
    print("\nRecords to migrate:")
    for i, (rid, meta) in enumerate(zip(ids, metas), 1):
        title = (meta or {}).get("title") or (meta or {}).get("institution") or "(untitled)"
        user = (meta or {}).get("user_id", "?")
        print(f"  {i:2d}. {title}   [user_id={user}]  id={rid}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to migrate.")
        return 0

    target = client.get_or_create_collection(
        name=target_name,
        metadata={"hnsw:space": "cosine"},
    )
    before = target.count()

    for start in range(0, len(ids), BATCH):
        end = start + BATCH
        kwargs = {
            "ids": ids[start:end],
            "documents": docs[start:end],
            "metadatas": metas[start:end],
        }
        if embs is not None and len(embs) == len(ids):
            kwargs["embeddings"] = embs[start:end]
        target.upsert(**kwargs)

    after = target.count()
    print(f"\nTarget collection: {before} -> {after} record(s).")

    # Verify every legacy id is now retrievable from the target
    check = target.get(ids=list(ids), include=["metadatas"])
    migrated = set(check.get("ids") or [])
    missing = [i for i in ids if i not in migrated]
    if missing:
        print(f"VERIFICATION FAILED — {len(missing)} id(s) missing from target: {missing[:5]}")
        print("Legacy collection left untouched.")
        return 1

    print(f"VERIFIED — all {len(ids)} record(s) present in '{target_name}'.")

    if args.delete_legacy:
        client.delete_collection(name=legacy_name)
        print(f"Deleted legacy collection '{legacy_name}'.")
    else:
        print(f"Legacy collection '{legacy_name}' kept. "
              f"Re-run with --delete-legacy once you are satisfied.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
