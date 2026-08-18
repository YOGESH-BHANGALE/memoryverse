"""
Tests for the ingestion pipeline.
"""

import pytest
from app.core.ingestion.parser import TextParser, PDFParser
from app.core.ingestion.categorizer import Categorizer
from app.core.ingestion.normalizer import normalise_payload
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


class TestPDFParserResilience:
    def test_garbage_bytes_do_not_raise(self):
        # A non-PDF (or encrypted/corrupt) payload must not escape as an HTTP
        # 500. PyPDF2 raises, the pdfplumber fallback also raises, and both are
        # now swallowed into an empty RawDocument that the ingest route rejects
        # with a clean 400 instead.
        result = PDFParser.parse(b"this is definitely not a pdf", "broken.pdf")
        assert result.text == ""
        assert result.file_type == FileType.PDF
        assert result.page_count == 0


class TestDiplomaReclassification:
    """Fix: 'Diploma' alone must not reclassify a course certificate as an
    academic record — it needs a corroborating institution signal."""

    def test_online_course_diploma_stays_a_certification(self):
        out = normalise_payload({
            "certifications": [
                {"name": "Diploma in Python Programming", "issuer": "Udemy"},
            ]
        })
        assert "Diploma in Python Programming" in [c["name"] for c in out["certification"]]
        assert out["academics"] == []

    def test_polytechnic_diploma_moves_to_academics(self):
        out = normalise_payload({
            "certifications": [
                {"name": "Diploma in Mechanical Engineering",
                 "issuer": "Government Polytechnic, Pune"},
            ]
        })
        assert out["certification"] == []
        assert len(out["academics"]) == 1

    def test_a_real_degree_moves_without_an_institution_word(self):
        # Unambiguous degree words are decisive on their own.
        out = normalise_payload({
            "certifications": [
                {"name": "Bachelor of Engineering in Computer Science",
                 "issuer": "DYPIT"},
            ]
        })
        assert out["certification"] == []
        assert len(out["academics"]) == 1

    def test_a_plain_professional_cert_is_untouched(self):
        out = normalise_payload({
            "certifications": [
                {"name": "AWS Certified Solutions Architect",
                 "issuer": "Amazon Web Services"},
            ]
        })
        assert len(out["certification"]) == 1
        assert out["academics"] == []


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
