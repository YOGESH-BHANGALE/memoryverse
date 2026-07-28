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
