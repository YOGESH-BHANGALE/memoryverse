"""
Tests for utility helpers and schemas.
"""

import asyncio

import pytest
from app.core.rag.intent import detect_intent
from app.utils.helpers import detect_file_type, normalise_date, sanitise_filename
from app.models.schemas import EntityCategory, FileType, SearchResult, SourceDocument


def _run(coro):
    """
    Drive one coroutine to completion.

    The suite has no pytest-asyncio, and adding it to run six assertions over a
    function that awaits nothing would be a dependency for no gain.
    """
    return asyncio.run(coro)


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


# ── Query Intent Router (Module 5) ─────────────────────────────────────

class TestDetectIntent:
    """
    The four query patterns the hackathon brief names explicitly, plus the
    disambiguation cases that make them work.
    """

    def test_show_all_my_certificates(self):
        intent = detect_intent("show all my certificates")
        assert intent.categories == (EntityCategory.CERTIFICATION,)
        # A list request, not a file request — "certificate" names a category
        # here, so it must not be read as "give me the PDF".
        assert intent.wants_documents is False

    def test_show_my_ai_projects(self):
        intent = detect_intent("show my AI projects")
        assert intent.categories == (EntityCategory.PROJECT,)

    def test_show_internship_documents(self):
        intent = detect_intent("show internship documents")
        assert intent.categories == (EntityCategory.INTERNSHIP,)
        # Both: the internship entities answer it, and each carries the file_id
        # of the document it came from.
        assert intent.wants_documents is True

    def test_show_my_latest_resume(self):
        intent = detect_intent("show my latest resume")
        assert intent.wants_documents is True
        assert intent.wants_latest is True
        assert intent.doc_hint == "resume"
        # No category — a resume is a document, not an entity type.
        assert intent.categories == ()

    def test_certificate_pdf_is_a_document_request(self):
        intent = detect_intent("show my certificate pdf")
        assert intent.categories == (EntityCategory.CERTIFICATION,)
        assert intent.wants_documents is True

    def test_multiple_categories(self):
        intent = detect_intent("my projects and internships")
        assert set(intent.categories) == {
            EntityCategory.PROJECT, EntityCategory.INTERNSHIP
        }

    def test_unrecognised_query_falls_through(self):
        intent = detect_intent("what did I learn about myself last summer")
        assert intent.is_empty
        assert intent.describe() == "none"

    def test_empty_query(self):
        assert detect_intent("").is_empty
        assert detect_intent("   ").is_empty

    def test_none_query_does_not_raise(self):
        assert detect_intent(None).is_empty  # type: ignore[arg-type]

    def test_word_boundaries(self):
        # "won" must not fire on "wonder", "cv" must not fire on "cvs"
        assert detect_intent("I wonder what happened").is_empty
        assert detect_intent("the cvs pharmacy trip").is_empty

    def test_describe_is_readable(self):
        assert detect_intent("show my latest resume").describe() == (
            "documents:resume; latest"
        )
        assert detect_intent("my skills").describe() == "categories=skill"
        # Category and document request must read as two separate facts.
        assert detect_intent("show internship documents").describe() == (
            "categories=internship; documents"
        )

    def test_document_hints_fall_back_to_the_category(self):
        # "internship documents" names no document type, so the category name is
        # the hint that narrows the file list.
        assert detect_intent("show internship documents").document_hints == (
            "internship",
        )
        # A specific type is tried before the category.
        assert detect_intent("my internship offer letter").document_hints[0] == (
            "offer letter"
        )

    def test_no_document_hints_when_nothing_recognised(self):
        assert detect_intent("hello there").document_hints == ()

    def test_categories_are_deduplicated(self):
        # Two phrases from the same category fire once.
        intent = detect_intent("my certificates and certifications")
        assert intent.categories == (EntityCategory.CERTIFICATION,)


class TestSourceDocument:
    def test_download_url_is_serialised(self):
        doc = SourceDocument(file_id="abc-123", source_file="Resume.pdf")
        dumped = doc.model_dump()
        # A bare @property would be missing here, leaving the UI with no link.
        assert dumped["download_url"] == "/api/files/abc-123"

    def test_link_ingest_without_file_id_has_no_url(self):
        doc = SourceDocument(source_file="https://github.com/someone")
        assert doc.model_dump()["download_url"] == ""


class _FakeChroma:
    """Minimal stand-in for ChromaClient.get_all over a fixed corpus."""

    def __init__(self, by_collection: dict[str, list[dict]]) -> None:
        self.by_collection = by_collection

    def get_all(self, collection_name: str, where=None, limit=None):
        return {"metadatas": self.by_collection.get(collection_name, [])}


def _retriever(by_collection: dict[str, list[dict]]):
    """
    Build a HybridRetriever without touching the embedding model or Chroma.

    ``__init__`` loads a Sentence-Transformers model, which a document-listing
    test has no use for, so bypass it and inject only what find_documents reads.
    """
    from app.core.rag.retriever import HybridRetriever

    retriever = object.__new__(HybridRetriever)
    retriever.chroma = _FakeChroma(by_collection)
    retriever.embedding_service = None
    return retriever


class TestFindDocuments:
    """
    Document listing and its narrowing rules.

    ``_resolve_original`` and ``_original_names`` touch the real upload directory,
    which these tests neither have nor need: both are patched to identity-ish
    behaviour so the assertions are about narrowing, not about disk state.
    """

    CHUNKS = [
        {"source_file": "Resume.pdf", "file_id": "f-resume", "file_type": "pdf"},
        {"source_file": "Resume.pdf", "file_id": "f-resume", "file_type": "pdf"},
        {"source_file": "Acme_Internship_Offer.pdf", "file_id": "f-offer",
         "file_type": "pdf"},
        {"source_file": "https://github.com/someone", "file_id": "",
         "file_type": "txt"},
    ]
    ENTITIES = {
        "internships": [{"file_id": "f-resume", "category": "internship"},
                        {"file_id": "f-offer", "category": "internship"}],
        "skills": [{"file_id": "f-resume", "category": "skill"},
                   {"file_id": "f-resume", "category": "skill"}],
    }

    @pytest.fixture
    def retriever(self, monkeypatch):
        from app.core.rag.retriever import HybridRetriever

        r = _retriever({"raw_chunks": self.CHUNKS, **self.ENTITIES})
        monkeypatch.setattr(
            HybridRetriever, "_resolve_original",
            staticmethod(lambda file_id, source_file: (file_id, "2026-01-01T00:00:00")),
        )
        monkeypatch.setattr(
            HybridRetriever, "_original_names",
            staticmethod(lambda: {"f-resume": "Resume.pdf",
                                  "f-offer": "Acme_Internship_Offer.pdf"}),
        )
        return r

    def test_lists_each_document_once_with_chunk_counts(self, retriever):
        docs = _run(retriever.find_documents(user_id="u"))
        assert {d.source_file: d.chunk_count for d in docs} == {
            "Resume.pdf": 2,
            "Acme_Internship_Offer.pdf": 1,
            "https://github.com/someone": 1,
        }

    def test_entity_counts_are_populated(self, retriever):
        docs = {d.source_file: d.entity_count
                for d in _run(retriever.find_documents(user_id="u"))}
        assert docs["Resume.pdf"] == 3        # 2 skills + 1 internship
        assert docs["Acme_Internship_Offer.pdf"] == 1
        assert docs["https://github.com/someone"] == 0

    def test_filename_hint_wins_over_category(self, retriever):
        # A file actually named for the thing beats provenance: that is the
        # document the user means by "my internship offer letter".
        docs = _run(retriever.find_documents(
            user_id="u", hints=("offer letter", "internship"),
            categories=(EntityCategory.INTERNSHIP,),
        ))
        assert [d.source_file for d in docs] == ["Acme_Internship_Offer.pdf"]

    def test_category_narrows_when_no_filename_matches(self, retriever):
        # "show internship documents": no filename contains "skill", so without
        # the category fallback this listed the GitHub link too.
        docs = _run(retriever.find_documents(
            user_id="u", hints=("skill",), categories=(EntityCategory.SKILL,),
        ))
        assert [d.source_file for d in docs] == ["Resume.pdf"]

    def test_unmatched_category_still_lists_everything(self, retriever):
        # No achievements were extracted from anything. Showing nothing would
        # hide the corpus; showing all of it at least answers "what do I have?".
        docs = _run(retriever.find_documents(
            user_id="u", categories=(EntityCategory.ACHIEVEMENT,),
        ))
        assert len(docs) == 3

    def test_latest_only_returns_one(self, retriever):
        docs = _run(retriever.find_documents(
            user_id="u", hints=("resume",), latest_only=True,
        ))
        assert len(docs) == 1 and docs[0].source_file == "Resume.pdf"
