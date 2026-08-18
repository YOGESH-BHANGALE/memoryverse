"""
Categorizer — routes extracted entities into typed, scored buckets.
"""

from __future__ import annotations

import hashlib
import re

from app.models.schemas import (
    CategorisedEntity,
    EntityCategory,
    ExtractionResult,
)
from app.utils.helpers import date_range_start, normalise_date
from app.utils.logger import logger


def stable_entity_id(user_id: str, category: EntityCategory, title: str) -> str:
    """
    Deterministic ID for an entity, derived from (user, category, title).

    Entities used to get a fresh ``uuid4()`` on every ingest, so re-uploading a
    document duplicated all of its entities — the certifications collection ended
    up holding "Programming in Java" twice. A content-derived ID makes the Chroma
    upsert idempotent: the same certification from the same user collapses onto
    one record no matter how many times it is uploaded.

    ``user_id`` is part of the digest because collections are shared across
    users; without it two people who both know Python would collide on one row.

    The title is lowercased, whitespace-collapsed and stripped of trailing
    punctuation, so "Traveo", "traveo" and "Traveo." resolve to one entity —
    all three spellings showed up in the same corpus.
    """
    normalised = re.sub(r"\s+", " ", title).strip().strip(".,;:!-–—_ ").lower()
    key = f"{user_id}|{category.value}|{normalised}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def entity_date(category: EntityCategory, data: dict) -> str | None:
    """
    Derive an entity's timeline date from its extracted fields.

    Every category is normalised to *when the thing began*, because the timeline
    is a chronological journey and mixing start dates for some categories with
    completion dates for others scrambles the ordering. A degree therefore shows
    up at enrolment rather than at its expected graduation, which for an
    in-progress course would otherwise place it in the future, after everything
    the student has actually done.

    Each field is tried through ``normalise_date`` first and then
    ``date_range_start``: the LLM frequently returns a whole range in a
    single-date field ("Jul 2025 - Oct 2025" as a certification's ``date``), and
    without the range fallback those entities ended up undated and silently
    dropped out of the dated timeline.

    Lives here rather than inline in ``categorise`` so the backfill script can
    recompute dates for entities that were stored before the fallback existed.
    """
    fields: tuple[str, ...]
    if category is EntityCategory.PROJECT:
        fields = ("date_range", "start_date", "date")
    elif category in (EntityCategory.INTERNSHIP, EntityCategory.ACADEMICS):
        fields = ("start_date", "date_range", "date", "end_date")
    else:
        fields = ("date", "date_range", "start_date", "end_date")

    for field in fields:
        raw = data.get(field)
        if not raw or not isinstance(raw, str):
            continue
        resolved = normalise_date(raw) or date_range_start(raw)
        if resolved:
            return resolved
    return None


class Categorizer:
    """
    Takes an ExtractionResult and flattens it into a list of
    CategorisedEntity objects with importance scores and tags.
    """

    def categorise(
        self,
        extraction: ExtractionResult,
        user_id: str = "default",
    ) -> list[CategorisedEntity]:
        """Convert all extracted entities into categorised, scored entities."""
        entities: list[CategorisedEntity] = []

        def _add(
            category: EntityCategory,
            title: str,
            data: dict,
            importance: int,
            tags: list[str],
            date: str | None,
        ) -> None:
            """Append an entity, skipping blanks and collapsing duplicates."""
            title = (title or "").strip()
            if not title:
                return
            entities.append(CategorisedEntity(
                id=stable_entity_id(user_id, category, title),
                category=category,
                title=title,
                data=data,
                importance_score=importance,
                tags=[t.strip() for t in tags if t and t.strip()],
                date=date,
            ))

        # ── Certifications ──────────────────────────────────────────────
        for cert in extraction.certifications:
            _add(
                EntityCategory.CERTIFICATION,
                cert.name,
                cert.model_dump(),
                self._score_certification(cert),
                [cert.issuer] if cert.issuer else [],
                entity_date(EntityCategory.CERTIFICATION, cert.model_dump()),
            )

        # ── Skills ──────────────────────────────────────────────────────
        for skill in extraction.skills:
            _add(
                EntityCategory.SKILL,
                skill.name,
                skill.model_dump(),
                self._score_skill(skill),
                [skill.category] if skill.category else [],
                None,
            )

        # ── Projects ────────────────────────────────────────────────────
        for proj in extraction.projects:
            _add(
                EntityCategory.PROJECT,
                proj.name,
                proj.model_dump(),
                self._score_project(proj),
                proj.tech_stack[:10],
                entity_date(EntityCategory.PROJECT, proj.model_dump()),
            )

        # ── Internships ─────────────────────────────────────────────────
        for intern in extraction.internships:
            _add(
                EntityCategory.INTERNSHIP,
                f"{intern.role or 'Intern'} @ {intern.company}",
                intern.model_dump(),
                self._score_internship(intern),
                [intern.company],
                entity_date(EntityCategory.INTERNSHIP, intern.model_dump()),
            )

        # ── Achievements ────────────────────────────────────────────────
        for ach in extraction.achievements:
            _add(
                EntityCategory.ACHIEVEMENT,
                ach.title,
                ach.model_dump(),
                self._score_achievement(ach),
                [],
                entity_date(EntityCategory.ACHIEVEMENT, ach.model_dump()),
            )

        # ── Academics ───────────────────────────────────────────────────
        for acad in extraction.academics:
            _add(
                EntityCategory.ACADEMICS,
                f"{acad.degree or 'Degree'} @ {acad.institution}",
                acad.model_dump(),
                self._score_academic(acad),
                [acad.institution],
                entity_date(EntityCategory.ACADEMICS, acad.model_dump()),
            )

        # Collapse duplicates that shared a stable ID within this one document
        # (e.g. "Python" listed under both Skills and Technical Skills).
        deduped: dict[str, CategorisedEntity] = {}
        for entity in entities:
            existing = deduped.get(entity.id)
            # Keep the richer record when the same entity appears twice.
            if existing is None or len(str(entity.data)) > len(str(existing.data)):
                deduped[entity.id] = entity

        result = list(deduped.values())
        dropped = len(entities) - len(result)
        logger.info(
            f"Categorized {len(result)} entities"
            + (f" ({dropped} duplicate(s) collapsed)" if dropped else "")
        )
        return result

    # ── Scoring Heuristics ──────────────────────────────────────────────

    @staticmethod
    def _score_certification(cert) -> int:
        score = 6
        if cert.credential_id:
            score += 2
        if cert.issuer and any(
            k in cert.issuer.lower()
            for k in ("google", "aws", "microsoft", "meta", "coursera")
        ):
            score += 1
        return min(score, 10)

    @staticmethod
    def _score_skill(skill) -> int:
        level_map = {"advanced": 8, "intermediate": 6, "beginner": 4}
        return level_map.get((skill.level or "").lower(), 5)

    @staticmethod
    def _score_project(proj) -> int:
        score = 5
        if proj.tech_stack:
            score += min(len(proj.tech_stack), 3)
        if proj.url:
            score += 1
        if proj.description and len(proj.description) > 50:
            score += 1
        return min(score, 10)

    @staticmethod
    def _score_internship(intern) -> int:
        score = 7  # internships are inherently high-value
        if intern.description and len(intern.description) > 50:
            score += 1
        if intern.end_date:
            score += 1
        return min(score, 10)

    @staticmethod
    def _score_achievement(ach) -> int:
        score = 6
        if ach.impact:
            score += 2
        if ach.description and len(ach.description) > 30:
            score += 1
        return min(score, 10)

    @staticmethod
    def _score_academic(acad) -> int:
        score = 6
        if acad.degree and len(acad.degree) > 5:
            score += 1
        if acad.description and len(acad.description) > 30:
            score += 1
        if acad.end_date:
            score += 1
        return min(score, 10)
