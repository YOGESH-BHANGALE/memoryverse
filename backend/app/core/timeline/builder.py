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
    MilestoneLink,
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
        entities, relations_by_id = self._fetch_all_entities(user_id)
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
        milestones = self._to_milestones(entities, relations_by_id)

        return TimelineResponse(
            user_id=user_id,
            milestones=milestones,
        )

    # ── Data Fetching ───────────────────────────────────────────────────

    def _fetch_all_entities(
        self, user_id: str
    ) -> tuple[list[CategorisedEntity], dict[str, list[dict]]]:
        """
        Pull all entities across typed collections for a user.

        Also returns each entity's persisted adjacency list, harvested from the
        very same metadata read. Relations used to be looked up one entity at a
        time against every collection in turn — roughly 1,700 Chroma queries for
        a 288-entity corpus, which dominated the timeline's response time.
        """
        entities: list[CategorisedEntity] = []
        relations_by_id: dict[str, list[dict]] = {}

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
                    relations_by_id[doc_id] = self._parse_relations(meta)
            except Exception as exc:
                logger.warning(f"Error fetching from {col_name}: {exc}")

        return entities, relations_by_id

    @staticmethod
    def _parse_relations(meta: dict) -> list[dict]:
        """Decode the ``relations`` metadata blob, tolerating malformed JSON."""
        raw = meta.get("relations") or "[]"
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return []
        return [r for r in parsed if isinstance(r, dict)] if isinstance(parsed, list) else []

    # ── Milestone Conversion ────────────────────────────────────────────

    def _to_milestones(
        self,
        entities: list[CategorisedEntity],
        relations_by_id: dict[str, list[dict]] | None = None,
    ) -> list[Milestone]:
        """
        Convert entities to timeline milestones.

        ``relations_by_id`` is optional: without it the milestones carry no
        connections, which is what a caller that only wants the chronology
        (or a test constructing entities by hand) should get.
        """
        relations_by_id = relations_by_id or {}
        milestones: list[Milestone] = []
        for entity in entities:
            links = self._to_links(relations_by_id.get(entity.id, []))

            milestones.append(Milestone(
                id=entity.id,
                date=entity.date,
                category=entity.category,
                title=entity.title,
                description=self._build_description(entity),
                # Kept as bare IDs for backwards compatibility; `related` is the
                # richer form that carries titles and the reason for each edge.
                related_entities=[link.id for link in links],
                related=links,
                importance_score=entity.importance_score,
                tags=entity.tags,
            ))
        return milestones

    @staticmethod
    def _to_links(relations: list[dict]) -> list[MilestoneLink]:
        """
        Turn persisted adjacency entries into readable milestone links.

        Entries written before the explainable engine landed carry only a
        ``target_id`` and a ``relation_type``; those still render, just without a
        title or a reason. Highest-confidence edges come first so the UI can
        truncate without dropping the most meaningful connection.
        """
        links: list[MilestoneLink] = []
        for rel in relations:
            target_id = rel.get("target_id")
            if not target_id:
                continue
            try:
                confidence = float(rel.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            links.append(MilestoneLink(
                id=str(target_id),
                title=str(rel.get("target_title") or ""),
                category=str(rel.get("target_category") or ""),
                relation_type=str(rel.get("type") or rel.get("relation_type") or ""),
                label=str(rel.get("label") or ""),
                why=str(rel.get("why") or ""),
                confidence=round(confidence, 3),
                direction=str(rel.get("direction") or "out"),
            ))
        links.sort(key=lambda link: link.confidence, reverse=True)
        return links

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
        """
        Deprecated: superseded by the batched read in ``_fetch_all_entities``.

        Retained because it is the only single-entity relation lookup available
        to callers outside the timeline build; it costs one query per collection,
        so do not use it in a loop.
        """
        for col_name in COLLECTIONS:
            if col_name == "raw_chunks":
                continue
            try:
                col = self.chroma.get_collection(col_name)
                result = col.get(ids=[entity_id], include=["metadatas"])
                if result and result["ids"]:
                    relations = self._parse_relations(result["metadatas"][0] or {})
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
