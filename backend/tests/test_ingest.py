"""
Tests for the ingestion pipeline.
"""

import pytest
from app.core.ingestion.parser import TextParser
from app.core.ingestion.categorizer import Categorizer
from app.models.schemas import (
    ExtractionResult,
    Skill,
    Project,
    Certification,
    Internship,
    Achievement,
    FileType,
)


class TestTextParser:
    def test_parse_plain_text(self):
        content = b"Hello, this is a test document."
        result = TextParser.parse(content, "test.txt")
        assert result.text == "Hello, this is a test document."
        assert result.filename == "test.txt"
        assert result.file_type == FileType.TXT
        assert result.page_count == 1

    def test_parse_empty_file(self):
        result = TextParser.parse(b"", "empty.txt")
        assert result.text == ""

    def test_parse_unicode(self):
        content = "Héllo wörld résumé".encode("utf-8")
        result = TextParser.parse(content, "unicode.txt")
        assert "résumé" in result.text


class TestCategorizer:
    def setup_method(self):
        self.categorizer = Categorizer()

    def test_categorise_skills(self):
        extraction = ExtractionResult(
            skills=[
                Skill(name="Python", level="advanced", category="language"),
                Skill(name="React", level="intermediate", category="framework"),
            ]
        )
        entities = self.categorizer.categorise(extraction)
        assert len(entities) == 2
        assert entities[0].title == "Python"
        assert entities[0].importance_score == 8  # advanced
        assert entities[1].importance_score == 6  # intermediate

    def test_categorise_project_with_tech_stack(self):
        extraction = ExtractionResult(
            projects=[
                Project(
                    name="MemoryVerse AI",
                    description="A personal knowledge management tool built with modern tech",
                    tech_stack=["Python", "FastAPI", "ChromaDB", "Next.js"],
                    url="https://github.com/example",
                )
            ]
        )
        entities = self.categorizer.categorise(extraction)
        assert len(entities) == 1
        assert entities[0].importance_score >= 8  # rich project

    def test_categorise_empty_extraction(self):
        extraction = ExtractionResult()
        entities = self.categorizer.categorise(extraction)
        assert len(entities) == 0

    def test_categorise_all_types(self):
        extraction = ExtractionResult(
            certifications=[Certification(name="AWS SAA", issuer="AWS")],
            skills=[Skill(name="Docker")],
            projects=[Project(name="Proj1")],
            internships=[Internship(company="Google", role="SWE Intern")],
            achievements=[Achievement(title="Hackathon Winner")],
        )
        entities = self.categorizer.categorise(extraction)
        assert len(entities) == 5
        categories = {e.category.value for e in entities}
        assert categories == {"certification", "skill", "project", "internship", "achievement"}
