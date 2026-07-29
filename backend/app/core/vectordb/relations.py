"""
Relationship Engine — builds and traverses entity cross-references.

Stores relations as metadata in ChromaDB so that we can traverse:
  Skill ──used_in──> Project
  Project ──validated_by──> Certificate
  Internship ──developed──> Skill
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from app.models.schemas import CategorisedEntity, EntityCategory
from app.core.vectordb.client import ChromaClient
from app.utils.logger import logger


# Relation types
RELATION_TYPES = {
    ("skill", "project"): "used_in",
    ("project", "certification"): "validated_by",
    ("internship", "skill"): "developed",
    ("skill", "internship"): "used_during",
    ("skill", "certification"): "certified_by",
    ("project", "achievement"): "led_to",
}


class RelationshipEngine:
    """
    Discovers and stores relationships between extracted entities
    using tag / keyword overlap and stores them as metadata cross-references.
    """

    def __init__(self) -> None:
        self.chroma = ChromaClient()

    def build_relations(
        self,
        entities: list[CategorisedEntity],
        user_id: str = "default",
    ) -> list[dict[str, Any]]:
        """
        Analyse a list of entities and return discovered relations.
        Each relation: { source_id, target_id, relation_type, relevance_score }
        """
        relations: list[dict[str, Any]] = []

        # Index entities by category for cross-matching
        by_category: dict[EntityCategory, list[CategorisedEntity]] = defaultdict(list)
        for e in entities:
            by_category[e.category].append(e)

        # ── Skill ↔ Project linking (via tech_stack overlap) ────────────
        for skill in by_category.get(EntityCategory.SKILL, []):
            skill_name = skill.title.lower()
            for project in by_category.get(EntityCategory.PROJECT, []):
                tech_stack = [t.lower() for t in project.data.get("tech_stack", [])]
                if skill_name in tech_stack or any(
                    skill_name in t or t in skill_name for t in tech_stack
                ):
                    score = self._compute_relevance(skill, project)
                    relations.append({
                        "source_id": skill.id,
                        "target_id": project.id,
                        "relation_type": "used_in",
                        "relevance_score": score,
                    })

        # ── Internship → Skill linking (keyword in description) ─────────
        for intern in by_category.get(EntityCategory.INTERNSHIP, []):
            desc = (intern.data.get("description") or "").lower()
            for skill in by_category.get(EntityCategory.SKILL, []):
                if skill.title.lower() in desc:
                    score = self._compute_relevance(intern, skill)
                    relations.append({
                        "source_id": intern.id,
                        "target_id": skill.id,
                        "relation_type": "developed",
                        "relevance_score": score,
                    })

        # ── Project → Certification (same domain keywords) ─────────────
        for project in by_category.get(EntityCategory.PROJECT, []):
            proj_words = set(
                project.title.lower().split()
                + [t.lower() for t in project.data.get("tech_stack", [])]
            )
            for cert in by_category.get(EntityCategory.CERTIFICATION, []):
                cert_words = set(cert.title.lower().split())
                overlap = proj_words & cert_words
                if overlap:
                    score = min(10, 5 + len(overlap) * 2)
                    relations.append({
                        "source_id": project.id,
                        "target_id": cert.id,
                        "relation_type": "validated_by",
                        "relevance_score": score,
                    })

        logger.info(f"Built {len(relations)} entity relations")
        return relations

    def store_relations(
        self,
        entities: list[CategorisedEntity],
        relations: list[dict[str, Any]],
    ) -> None:
        """
        Write relation metadata back into entity metadata in ChromaDB.
        Each entity gets a 'relations' JSON field listing its connections.
        """
        # Build adjacency map: entity_id → list of {target_id, relation_type, score}
        adj: dict[str, list[dict]] = defaultdict(list)
        for rel in relations:
            adj[rel["source_id"]].append({
                "target_id": rel["target_id"],
                "type": rel["relation_type"],
                "score": rel["relevance_score"],
            })
            # Reverse link
            adj[rel["target_id"]].append({
                "target_id": rel["source_id"],
                "type": f"reverse_{rel['relation_type']}",
                "score": rel["relevance_score"],
            })

        # Update metadata for affected entities
        entity_map = {e.id: e for e in entities}
        for entity_id, rels in adj.items():
            entity = entity_map.get(entity_id)
            if not entity:
                continue
            collection_name = f"{entity.category.value}s"
            try:
                col = self.chroma.get_collection(collection_name)
                existing = col.get(ids=[entity_id], include=["metadatas"])
                if existing and existing["metadatas"]:
                    meta = existing["metadatas"][0]
                    meta["relations"] = json.dumps(rels)
                    col.update(ids=[entity_id], metadatas=[meta])
            except Exception as exc:
                logger.warning(f"Failed to store relations for {entity_id}: {exc}")

    def get_related_entities(self, entity_id: str) -> list[dict[str, Any]]:
        """
        Traverse relations for a given entity by checking all collections
        for the entity and reading its 'relations' metadata.
        """
        from app.core.vectordb.client import COLLECTIONS

        for col_name in COLLECTIONS:
            if col_name == "raw_chunks":
                continue
            try:
                col = self.chroma.get_collection(col_name)
                result = col.get(ids=[entity_id], include=["metadatas"])
                if result and result["ids"]:
                    meta = result["metadatas"][0]
                    raw_relations = meta.get("relations", "[]")
                    return json.loads(raw_relations) if isinstance(raw_relations, str) else raw_relations
            except Exception:
                continue
        return []

    # ── Scoring ─────────────────────────────────────────────────────────

    @staticmethod
    def _compute_relevance(a: CategorisedEntity, b: CategorisedEntity) -> int:
        """Compute a 1-10 relevance score between two entities."""
        score = 5
        # Boost for tag overlap
        a_tags = set(t.lower() for t in a.tags)
        b_tags = set(t.lower() for t in b.tags)
        overlap = len(a_tags & b_tags)
        score += overlap * 2
        # Boost for high importance entities
        if a.importance_score >= 8 or b.importance_score >= 8:
            score += 1
        return min(score, 10)
