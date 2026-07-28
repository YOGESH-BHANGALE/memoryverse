"""
Categorizer — routes extracted entities into typed, scored buckets.
"""

from __future__ import annotations

from app.models.schemas import (
    CategorisedEntity,
    EntityCategory,
    ExtractionResult,
)
from app.utils.helpers import normalise_date
from app.utils.logger import logger


class Categorizer:
    """
    Takes an ExtractionResult and flattens it into a list of
    CategorisedEntity objects with importance scores and tags.
    """

    def categorise(self, extraction: ExtractionResult) -> list[CategorisedEntity]:
        """Convert all extracted entities into categorised, scored entities."""
        entities: list[CategorisedEntity] = []

        # ── Certifications ──────────────────────────────────────────────
        for cert in extraction.certifications:
            entities.append(CategorisedEntity(
                category=EntityCategory.CERTIFICATION,
                title=cert.name,
                data=cert.model_dump(),
                importance_score=self._score_certification(cert),
                tags=[cert.issuer] if cert.issuer else [],
                date=normalise_date(cert.date),
            ))

        # ── Skills ──────────────────────────────────────────────────────
        for skill in extraction.skills:
            entities.append(CategorisedEntity(
                category=EntityCategory.SKILL,
                title=skill.name,
                data=skill.model_dump(),
                importance_score=self._score_skill(skill),
                tags=[skill.category] if skill.category else [],
                date=None,
            ))

        # ── Projects ────────────────────────────────────────────────────
        for proj in extraction.projects:
            date_str = None
            if proj.date_range:
                # Take the start portion if it's a range
                parts = proj.date_range.split("–")
                if not parts:
                    parts = proj.date_range.split("-")
                date_str = normalise_date(parts[0].strip()) if parts else None

            entities.append(CategorisedEntity(
                category=EntityCategory.PROJECT,
                title=proj.name,
                data=proj.model_dump(),
                importance_score=self._score_project(proj),
                tags=proj.tech_stack[:10],
                date=date_str,
            ))

        # ── Internships ─────────────────────────────────────────────────
        for intern in extraction.internships:
            entities.append(CategorisedEntity(
                category=EntityCategory.INTERNSHIP,
                title=f"{intern.role or 'Intern'} @ {intern.company}",
                data=intern.model_dump(),
                importance_score=self._score_internship(intern),
                tags=[intern.company],
                date=normalise_date(intern.start_date),
            ))

        # ── Achievements ────────────────────────────────────────────────
        for ach in extraction.achievements:
            entities.append(CategorisedEntity(
                category=EntityCategory.ACHIEVEMENT,
                title=ach.title,
                data=ach.model_dump(),
                importance_score=self._score_achievement(ach),
                tags=[],
                date=normalise_date(ach.date),
            ))

        # ── Academics ───────────────────────────────────────────────────
        for acad in extraction.academics:
            entities.append(CategorisedEntity(
                category=EntityCategory.ACADEMICS,
                title=f"{acad.degree or 'Degree'} @ {acad.institution}",
                data=acad.model_dump(),
                importance_score=self._score_academic(acad),
                tags=[acad.institution],
                date=normalise_date(acad.end_date) or normalise_date(acad.start_date),
            ))

        logger.info(f"Categorized {len(entities)} entities")
        return entities

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
