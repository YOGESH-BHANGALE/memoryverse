"""
Tests for the Timeline Builder.
"""

import pytest
from app.core.timeline.builder import TimelineBuilder
from app.models.schemas import CategorisedEntity, EntityCategory, Milestone


class TestTimelineBuilder:
    def setup_method(self):
        self.builder = TimelineBuilder()

    def test_sort_key_with_date(self):
        assert self.builder._sort_key("2023-06") == "2023-06"

    def test_sort_key_without_date(self):
        assert self.builder._sort_key(None) == "9999-99"

    def test_matches_year_true(self):
        entity = CategorisedEntity(
            category=EntityCategory.PROJECT,
            title="Test",
            data={},
            date="2023-06",
        )
        assert self.builder._matches_year(entity, "2023") is True

    def test_matches_year_false(self):
        entity = CategorisedEntity(
            category=EntityCategory.PROJECT,
            title="Test",
            data={},
            date="2022-06",
        )
        assert self.builder._matches_year(entity, "2023") is False

    def test_matches_year_no_date(self):
        entity = CategorisedEntity(
            category=EntityCategory.SKILL,
            title="Python",
            data={},
            date=None,
        )
        assert self.builder._matches_year(entity, "2023") is False

    def test_build_description_with_rich_data(self):
        entity = CategorisedEntity(
            category=EntityCategory.INTERNSHIP,
            title="SWE Intern @ Google",
            data={
                "description": "Worked on search infrastructure",
                "role": "SWE Intern",
                "company": "Google",
            },
        )
        desc = self.builder._build_description(entity)
        assert "SWE Intern" in desc
        assert "Google" in desc

    def test_build_description_empty_data(self):
        entity = CategorisedEntity(
            category=EntityCategory.SKILL,
            title="Python",
            data={},
        )
        desc = self.builder._build_description(entity)
        assert desc == "Python"

    def test_to_milestones(self):
        entities = [
            CategorisedEntity(
                category=EntityCategory.PROJECT,
                title="Project A",
                data={"tech_stack": ["React", "Node"]},
                date="2023-01",
                importance_score=8,
                tags=["React", "Node"],
            ),
            CategorisedEntity(
                category=EntityCategory.CERTIFICATION,
                title="AWS SAA",
                data={"issuer": "AWS"},
                date="2023-06",
                importance_score=7,
            ),
        ]
        milestones = self.builder._to_milestones(entities)
        assert len(milestones) == 2
        assert all(isinstance(m, Milestone) for m in milestones)
        assert milestones[0].title == "Project A"


class TestMilestoneLinks:
    """Relation metadata -> readable milestone links."""

    def setup_method(self):
        self.builder = TimelineBuilder()

    def test_links_carry_title_and_reason(self):
        entity = CategorisedEntity(
            id="e1",
            category=EntityCategory.PROJECT,
            title="MemoryVerse AI",
            data={},
            date="2026-01",
        )
        relations = {"e1": [{
            "target_id": "s1",
            "target_title": "Python",
            "target_category": "skill",
            "type": "used_in",
            "direction": "in",
            "label": "Skill applied in a project",
            "why": '"python" is listed in this project\'s tech stack',
            "confidence": 0.6,
        }]}
        milestone = self.builder._to_milestones([entity], relations)[0]
        assert milestone.related_entities == ["s1"]
        assert milestone.related[0].title == "Python"
        assert milestone.related[0].relation_type == "used_in"
        assert milestone.related[0].why.startswith('"python" is listed')
        assert milestone.related[0].confidence == 0.6

    def test_links_sorted_by_confidence(self):
        entity = CategorisedEntity(id="e1", category=EntityCategory.PROJECT,
                                   title="P", data={})
        relations = {"e1": [
            {"target_id": "a", "target_title": "Weak", "confidence": 0.31},
            {"target_id": "b", "target_title": "Strong", "confidence": 0.92},
        ]}
        links = self.builder._to_milestones([entity], relations)[0].related
        assert [l.title for l in links] == ["Strong", "Weak"]

    def test_legacy_relations_without_titles_still_render(self):
        """Rows written before the explainable engine only have target_id."""
        entity = CategorisedEntity(id="e1", category=EntityCategory.SKILL,
                                   title="S", data={})
        relations = {"e1": [{"target_id": "old-uuid", "relation_type": "related_to"}]}
        link = self.builder._to_milestones([entity], relations)[0].related[0]
        assert link.id == "old-uuid"
        assert link.title == ""
        assert link.relation_type == "related_to"
        assert link.confidence == 0.0

    def test_relations_without_target_id_are_dropped(self):
        entity = CategorisedEntity(id="e1", category=EntityCategory.SKILL,
                                   title="S", data={})
        relations = {"e1": [{"target_title": "Orphan"}, {"target_id": "ok"}]}
        links = self.builder._to_milestones([entity], relations)[0].related
        assert [l.id for l in links] == ["ok"]

    def test_malformed_relations_json_is_tolerated(self):
        assert self.builder._parse_relations({"relations": "{not json"}) == []
        assert self.builder._parse_relations({"relations": None}) == []
        assert self.builder._parse_relations({}) == []
        # A JSON object rather than a list is also malformed for this field.
        assert self.builder._parse_relations({"relations": '{"a":1}'}) == []
        assert self.builder._parse_relations({"relations": '[{"target_id":"x"}]'}) \
            == [{"target_id": "x"}]

    def test_non_numeric_confidence_does_not_raise(self):
        entity = CategorisedEntity(id="e1", category=EntityCategory.SKILL,
                                   title="S", data={})
        relations = {"e1": [{"target_id": "x", "confidence": "high"}]}
        assert self.builder._to_milestones([entity], relations)[0].related[0].confidence == 0.0


class TestEntityDate:
    """Date derivation from messy extracted fields."""

    def test_range_in_single_date_field(self):
        from app.core.ingestion.categorizer import entity_date
        # The extractor puts a whole range in a certification's `date`.
        assert entity_date(EntityCategory.CERTIFICATION,
                           {"date": "Jul 2025 - Oct 2025"}) == "2025-07"

    def test_en_dash_range(self):
        from app.core.ingestion.categorizer import entity_date
        assert entity_date(EntityCategory.ACHIEVEMENT,
                           {"date": "Jan 2026 \u2013 May 2026"}) == "2026-01"

    def test_bare_year_range(self):
        from app.core.ingestion.categorizer import entity_date
        assert entity_date(EntityCategory.ACHIEVEMENT,
                           {"date": "2025 \u2013 2026"}) == "2025-01"

    def test_academics_prefers_enrolment_over_graduation(self):
        from app.core.ingestion.categorizer import entity_date
        # Graduation may be in the future; the journey starts at enrolment.
        assert entity_date(EntityCategory.ACADEMICS,
                           {"start_date": "Sep 2024", "end_date": "Jun 2028"}) == "2024-09"

    def test_unparseable_text_yields_none(self):
        from app.core.ingestion.categorizer import entity_date
        assert entity_date(EntityCategory.PROJECT, {"date_range": "ongoing research"}) is None
        assert entity_date(EntityCategory.PROJECT, {}) is None

    def test_non_string_field_is_ignored(self):
        from app.core.ingestion.categorizer import entity_date
        assert entity_date(EntityCategory.CERTIFICATION, {"date": 2025}) is None
