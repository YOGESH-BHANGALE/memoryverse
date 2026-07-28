"""
Entity conversion helpers — bridge between Pydantic schemas and ChromaDB docs.
"""

from __future__ import annotations

import json
from typing import Any

from app.models.schemas import CategorisedEntity, EntityCategory


def entity_to_document(entity: CategorisedEntity) -> dict[str, Any]:
    """Convert a CategorisedEntity to a ChromaDB-compatible document dict."""
    metadata = {
        "category": entity.category.value,
        "title": entity.title,
        "importance_score": entity.importance_score,
        "tags": json.dumps(entity.tags),
        "date": entity.date or "",
        "data_json": json.dumps(entity.data),
    }
    if entity.file_id:
        metadata["file_id"] = entity.file_id

    return {
        "id": entity.id,
        "document": f"{entity.title}: {json.dumps(entity.data)}",
        "metadata": metadata,
    }


def document_to_entity(doc_id: str, document: str, metadata: dict) -> CategorisedEntity:
    """Reconstruct a CategorisedEntity from a ChromaDB result."""
    tags_raw = metadata.get("tags", "[]")
    try:
        tags = json.loads(tags_raw) if isinstance(tags_raw, str) and tags_raw.strip() else (tags_raw if isinstance(tags_raw, list) else [])
    except (json.JSONDecodeError, ValueError):
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if isinstance(tags_raw, str) else []

    data_raw = metadata.get("data_json", "{}")
    try:
        data = json.loads(data_raw) if isinstance(data_raw, str) and data_raw.strip() else (data_raw if isinstance(data_raw, dict) else {})
    except (json.JSONDecodeError, ValueError):
        data = {}

    return CategorisedEntity(
        id=doc_id,
        category=EntityCategory(metadata.get("category", "skill")),
        title=metadata.get("title", ""),
        data=data,
        importance_score=int(metadata.get("importance_score", 5)),
        tags=tags,
        date=metadata.get("date") or None,
        file_id=metadata.get("file_id") or None,
    )
