"""
Timeline Builder — aggregates entities from ChromaDB into a chronological
journey timeline grouped by year and category.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Optional

from app.models.schemas import (
    CategorisedEntity,
    EntityCategory,
    Milestone,
    TimelineResponse,
)
from app.models.entities import document_to_entity
from app.core.vectordb.client import ChromaClient, COLLECTIONS
from app.utils.logger import logger


class TimelineBuilder:
    """
    Builds the Journey Timeline by:
    1. Aggregating all dated entities from ChromaDB
    2. Sorting chronologically
    3. Grouping by year and category
    4. Enriching each milestone with related entities
    """

    def __init__(self) -> None:
        self.chroma = ChromaClient()

    def build(
        self,
        user_id: str = "default",
        year: Optional[str] = None,
        category: Optional[str] = None,
    ) -> TimelineResponse:
        """
        Build the full timeline for a user, optionally filtered by year/category.
        """
        entities = self._fetch_all_entities(user_id)
        logger.info(f"Fetched {len(entities)} entities for user {user_id}")

        # Filter by year if specified
        if year:
            entities = [e for e in entities if self._matches_year(e, year)]

        # Filter by category if specified
        if category:
            try:
                cat_enum = EntityCategory(category)
                entities = [e for e in entities if e.category == cat_enum]
            except ValueError:
                pass

        # Sort chronologically
        entities.sort(key=lambda e: self._sort_key(e.date))

        # Convert to milestones
        milestones = self._to_milestones(entities)

        return TimelineResponse(
            user_id=user_id,
            milestones=milestones,
        )

    # ── Data Fetching ───────────────────────────────────────────────────

    def _fetch_all_entities(self, user_id: str) -> list[CategorisedEntity]:
        """Pull all entities across typed collections for a user."""
        entities: list[CategorisedEntity] = []

        for col_name in COLLECTIONS:
            if col_name == "raw_chunks":
                continue
            try:
                result = self.chroma.get_all(
                    collection_name=col_name,
                    where={"user_id": user_id},
                    limit=500,
                )
                if not result or not result.get("ids"):
                    continue
                for i, doc_id in enumerate(result["ids"]):
                    doc = result["documents"][i] if result.get("documents") else ""
                    meta = result["metadatas"][i] if result.get("metadatas") else {}
                    entity = document_to_entity(doc_id, doc, meta)
                    entities.append(entity)
            except Exception as exc:
                logger.warning(f"Error fetching from {col_name}: {exc}")

        return entities

    # ── Milestone Conversion ────────────────────────────────────────────

    def _to_milestones(self, entities: list[CategorisedEntity]) -> list[Milestone]:
        """Convert entities to timeline milestones."""
        milestones: list[Milestone] = []
        for entity in entities:
            # Fetch relations if available
            related_ids = self._get_related_ids(entity.id)

            milestones.append(Milestone(
                id=entity.id,
                date=entity.date,
                category=entity.category,
                title=entity.title,
                description=self._build_description(entity),
                related_entities=related_ids,
                importance_score=entity.importance_score,
                tags=entity.tags,
            ))
        return milestones

    def _build_description(self, entity: CategorisedEntity) -> str:
        """Generate a human-readable description from entity data."""
        data = entity.data
        parts: list[str] = []

        if "description" in data and data["description"]:
            parts.append(data["description"])
        if "role" in data and data["role"]:
            parts.append(f"Role: {data['role']}")
        if "company" in data and data["company"]:
            parts.append(f"Company: {data['company']}")
        if "issuer" in data and data["issuer"]:
            parts.append(f"Issuer: {data['issuer']}")
        if "tech_stack" in data and data["tech_stack"]:
            parts.append(f"Tech: {', '.join(data['tech_stack'])}")
        if "impact" in data and data["impact"]:
            parts.append(f"Impact: {data['impact']}")
        if "level" in data and data["level"]:
            parts.append(f"Level: {data['level']}")

        return " | ".join(parts) if parts else entity.title

    def _get_related_ids(self, entity_id: str) -> list[str]:
        """Retrieve related entity IDs from metadata."""
        for col_name in COLLECTIONS:
            if col_name == "raw_chunks":
                continue
            try:
                col = self.chroma.get_collection(col_name)
                result = col.get(ids=[entity_id], include=["metadatas"])
                if result and result["ids"]:
                    meta = result["metadatas"][0]
                    raw = meta.get("relations", "[]")
                    relations = json.loads(raw) if isinstance(raw, str) else raw
                    return [r["target_id"] for r in relations if "target_id" in r]
            except Exception:
                continue
        return []

    # ── Sorting Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _sort_key(date: Optional[str]) -> str:
        """Convert a date string to a sortable key. Undated items go last."""
        if not date:
            return "9999-99"
        return date

    @staticmethod
    def _matches_year(entity: CategorisedEntity, year: str) -> bool:
        """Check whether an entity's date falls within the given year."""
        if not entity.date:
            return False
        return entity.date.startswith(year)
