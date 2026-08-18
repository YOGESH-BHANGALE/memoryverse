"""
Query intent detection — maps a natural-language question onto the categories
(and documents) it is actually asking about.

Why this exists
---------------
Hybrid retrieval alone answers "show all my certificates" badly. The phrase
carries almost no lexical overlap with a certification record — a row that reads
"Introduction to Machine Learning | Issuer: NPTEL" shares no rare term with the
query — so BM25 contributes nothing and the semantic score spreads thinly across
every collection. Measured on a real 103-entity corpus, that query returned one
certification among eight results, padded out with skills and achievements.

The category the user named is right there in the question, so read it. Once the
search is restricted to the certifications collection, every result is a
certificate and ranking within them barely matters.

Detection is deliberately rule-based rather than an LLM call. It runs in
microseconds on the request path, it cannot fail with malformed JSON, and its
behaviour is testable — an intent classifier that occasionally hallucinates
"academics" for "show my certificates" would be worse than no router at all.
Anything unrecognised falls through to unrestricted hybrid search, so a missed
pattern degrades to the previous behaviour rather than to an error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from app.models.schemas import EntityCategory

# Phrases that name a category. Matched on word boundaries against the
# lowercased query, longest first so "work experience" wins over "work".
_CATEGORY_PATTERNS: tuple[tuple[EntityCategory, tuple[str, ...]], ...] = (
    (EntityCategory.CERTIFICATION, (
        "certifications", "certification", "certificates", "certificate",
        "certified", "credentials", "credential", "licences", "licenses",
        "badges", "badge", "nptel", "coursera", "udemy",
    )),
    (EntityCategory.INTERNSHIP, (
        "internships", "internship", "interned", "intern",
        "work experience", "work history", "employment", "jobs", "job",
        "companies i worked", "where i worked", "professional experience",
    )),
    (EntityCategory.PROJECT, (
        "projects", "project", "portfolio pieces", "things i built",
        "what i built", "apps i", "applications i", "repos", "repositories",
    )),
    (EntityCategory.SKILL, (
        "skills", "skill", "technologies", "technology", "tech stack",
        "tools i", "languages i", "programming languages", "frameworks",
        "expertise", "proficient", "what do i know", "what i know",
    )),
    (EntityCategory.ACHIEVEMENT, (
        "achievements", "achievement", "accomplishments", "accomplishment",
        "awards", "award", "prizes", "prize", "honours", "honors",
        "hackathons", "hackathon", "competitions", "won", "wins",
        "recognitions", "recognition",
    )),
    (EntityCategory.ACADEMICS, (
        "academics", "academic", "education", "educational", "degree",
        "degrees", "college", "university", "school", "cgpa", "gpa",
        "semester", "coursework", "transcript", "marksheet", "grades",
    )),
)

# Phrases that ask for an original file rather than for extracted facts.
_DOCUMENT_TERMS: tuple[str, ...] = (
    "resume", "resumes", "cv", "curriculum vitae", "document", "documents",
    "docs", "files", "file", "pdf", "pdfs", "original", "originals",
    "offer letter", "offer letters", "letter", "letters", "attachment",
    "attachments", "upload", "uploads", "uploaded",
)

# Words hinting the newest item is wanted, not the whole set.
_RECENCY_TERMS: tuple[str, ...] = (
    "latest", "newest", "most recent", "recent", "last", "current",
)

# A document-type hint used to pick between several stored files.
_DOC_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("resume", ("resume", "cv", "curriculum vitae")),
    ("certificate", ("certificate", "certification", "credential")),
    ("offer letter", ("offer letter", "internship letter", "offer")),
    ("transcript", ("transcript", "marksheet", "grade")),
    ("report", ("report", "project report")),
)


@dataclass(frozen=True)
class QueryIntent:
    """What a query is asking for, beyond its literal words."""

    categories: tuple[EntityCategory, ...] = ()
    wants_documents: bool = False     # asking for the original file itself
    wants_latest: bool = False        # only the most recent one
    doc_hint: str = ""                # "resume", "offer letter", …
    matched: tuple[str, ...] = field(default_factory=tuple)  # phrases that fired

    @property
    def is_empty(self) -> bool:
        """True when nothing was recognised and search should stay unrestricted."""
        return not self.categories and not self.wants_documents

    @property
    def document_hints(self) -> tuple[str, ...]:
        """
        Filename hints to try, most specific first.

        "show internship documents" names no document *type*, so without the
        category as a fallback hint it matched nothing and listed every file the
        user had ever ingested — question banks and GitHub repos included. The
        category name is a good filename hint in practice, because uploads are
        named for what they are ("Acme_Corp_Internship_Offer.pdf").
        """
        hints = [self.doc_hint] if self.doc_hint else []
        hints.extend(c.value for c in self.categories)
        return tuple(dict.fromkeys(h for h in hints if h))

    def describe(self) -> str:
        """
        One line for logs and for the API's `intent` field.

        Parts are separated by "; " because space-joining them read as one value:
        "categories=internship documents" looked like a category called
        "internship documents" rather than a category plus a document request.

        ``wants_latest`` is only reported when something was actually recognised.
        Recency alone is not an intent — "what did I learn last summer" trips the
        "last" term but restricts nothing, and reporting "latest" there would
        claim the router did something it did not.
        """
        parts: list[str] = []
        if self.categories:
            parts.append("categories=" + ",".join(c.value for c in self.categories))
        if self.wants_documents:
            parts.append("documents" + (f":{self.doc_hint}" if self.doc_hint else ""))
        if self.wants_latest and not self.is_empty:
            parts.append("latest")
        return "; ".join(parts) or "none"


@lru_cache(maxsize=512)
def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    r"""
    Word-boundary matcher for a phrase.

    ``\b`` alone is not enough on either end: "won" must not match "wonder" and
    "cv" must not match "cvs" in a filename, while "c++"-style phrases never
    appear in this table so escaping is sufficient elsewhere.
    """
    return re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])")


def _contains(haystack: str, phrase: str) -> bool:
    return bool(_phrase_pattern(phrase).search(haystack))


def detect_intent(query: str) -> QueryIntent:
    """
    Read the categories and document requests out of a natural-language query.

    Multiple categories can fire at once ("my projects and internships"), in
    which case the search covers all of them. "show internship documents" is
    both an internship query and a document request: the internship entities are
    what answer it, and they each carry the file_id of the document they came
    from, so the caller can link back to the original.
    """
    text = (query or "").lower()
    if not text.strip():
        return QueryIntent()

    categories: list[EntityCategory] = []
    matched: list[str] = []

    for category, phrases in _CATEGORY_PATTERNS:
        for phrase in sorted(phrases, key=len, reverse=True):
            if _contains(text, phrase):
                categories.append(category)
                matched.append(phrase)
                break  # one hit is enough to claim the category

    doc_terms = [t for t in _DOCUMENT_TERMS if _contains(text, t)]
    wants_latest = any(_contains(text, t) for t in _RECENCY_TERMS)

    doc_hint = ""
    for hint, aliases in _DOC_HINTS:
        if any(_contains(text, a) for a in aliases):
            doc_hint = hint
            break

    # "certificate" is in both tables: it names a category *and* is a kind of
    # document. Treat it as a document request only when the query also asks for
    # a file — "show my certificates" wants the list, "show my certificate pdf"
    # wants the file.
    generic_doc_terms = [
        t for t in doc_terms
        if not any(_contains(t, p) for _, phrases in _CATEGORY_PATTERNS for p in phrases)
    ]
    wants_documents = bool(generic_doc_terms)

    matched.extend(generic_doc_terms)

    return QueryIntent(
        categories=tuple(dict.fromkeys(categories)),
        wants_documents=wants_documents,
        wants_latest=wants_latest,
        doc_hint=doc_hint,
        matched=tuple(dict.fromkeys(matched)),
    )
