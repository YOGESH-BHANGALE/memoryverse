"""
Tests for utility helpers and schemas.
"""

import pytest
from app.utils.helpers import detect_file_type, normalise_date, sanitise_filename
from app.models.schemas import FileType, SearchResult


class TestDetectFileType:
    def test_pdf(self):
        assert detect_file_type("resume.pdf") == FileType.PDF

    def test_txt(self):
        assert detect_file_type("notes.txt") == FileType.TXT

    def test_docx(self):
        assert detect_file_type("doc.docx") == FileType.DOCX

    def test_unsupported(self):
        with pytest.raises(ValueError):
            detect_file_type("image.png")


class TestNormaliseDate:
    def test_already_normalised(self):
        assert normalise_date("2023-06") == "2023-06"

    def test_full_date(self):
        assert normalise_date("2023-06-15") == "2023-06"

    def test_month_year(self):
        assert normalise_date("January 2023") == "2023-01"

    def test_short_month_year(self):
        assert normalise_date("Mar 2024") == "2024-03"

    def test_year_only(self):
        assert normalise_date("2023") == "2023-01"

    def test_none(self):
        assert normalise_date(None) is None

    def test_unparseable(self):
        assert normalise_date("sometime last year") is None


class TestSanitiseFilename:
    def test_normal(self):
        assert sanitise_filename("my_file.pdf") == "my_file.pdf"

    def test_spaces(self):
        assert sanitise_filename("my file.pdf") == "my_file.pdf"

    def test_special_chars(self):
        result = sanitise_filename("résumé (2).pdf")
        assert "(" not in result
        assert ")" not in result


class TestSearchResult:
    def test_create(self):
        sr = SearchResult(id="1", text="hello", score=0.95)
        assert sr.id == "1"
        assert sr.score == 0.95
        assert sr.metadata == {}
