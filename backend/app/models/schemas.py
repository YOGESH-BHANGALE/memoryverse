"""
Pydantic schemas — request / response models for the API layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field, field_validator


# ── Enums ───────────────────────────────────────────────────────────────

class FileType(str, Enum):
    PDF = "pdf"
    TXT = "txt"
    DOCX = "docx"


class EntityCategory(str, Enum):
    SKILL = "skill"
    PROJECT = "project"
    CERTIFICATION = "certification"
    INTERNSHIP = "internship"
    ACHIEVEMENT = "achievement"
    ACADEMICS = "academics"


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Raw Document ────────────────────────────────────────────────────────

class RawDocument(BaseModel):
    """Normalised output from any file parser."""
    text: str
    filename: str
    file_type: FileType
    page_count: int = 1
    file_id: Optional[str] = None


# ── Extracted Entities ──────────────────────────────────────────────────

class Certification(BaseModel):
    name: str
    issuer: Optional[str] = None
    date: Optional[str] = None
    credential_id: Optional[str] = None


class Skill(BaseModel):
    name: str
    level: Optional[str] = None          # beginner / intermediate / advanced
    category: Optional[str] = None       # language, framework, tool, soft-skill


class Project(BaseModel):
    name: str
    description: Optional[str] = None
    tech_stack: list[str] = Field(default_factory=list)
    date_range: Optional[str] = None     # "Jan 2023 – Mar 2023"
    url: Optional[str] = None


class Internship(BaseModel):
    company: str
    role: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None


class Achievement(BaseModel):
    title: str
    description: Optional[str] = None
    date: Optional[str] = None
    impact: Optional[str] = None


class Academic(BaseModel):
    institution: str
    degree: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None


class ExtractionResult(BaseModel):
    """Aggregated extraction output from the LLM."""
    certifications: list[Certification] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    internships: list[Internship] = Field(default_factory=list)
    achievements: list[Achievement] = Field(default_factory=list)
    academics: list[Academic] = Field(default_factory=list)


# ── Categorised Entity ─────────────────────────────────────────────────

class CategorisedEntity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    category: EntityCategory
    title: str
    data: dict                           # raw entity dict
    importance_score: int = Field(ge=1, le=10, default=5)
    tags: list[str] = Field(default_factory=list)
    date: Optional[str] = None
    file_id: Optional[str] = None


# ── Ingestion ───────────────────────────────────────────────────────────

class LinkIngestionRequest(BaseModel):
    url: str

class IngestionResult(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.COMPLETED
    filename: str
    entities_extracted: int = 0
    entities: list[CategorisedEntity] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class IngestionStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: Optional[str] = None


# ── Timeline ────────────────────────────────────────────────────────────

class MilestoneLink(BaseModel):
    """
    A readable pointer from one milestone to a connected entity.

    The timeline used to expose related entities as bare UUIDs, which meant the
    UI had to issue a second request per milestone just to learn their names.
    The relationship engine already persists the target's title and the reason
    for the edge, so the timeline carries them straight through.
    """
    id: str
    title: str
    category: str
    relation_type: str = ""
    label: str = ""                      # e.g. "Skill applied in a project"
    why: str = ""                        # concrete evidence, "; "-joined
    confidence: float = 0.0
    direction: str = "out"               # "out" = this milestone is the source


class Milestone(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    date: Optional[str] = None           # YYYY-MM or free text
    category: EntityCategory
    title: str
    description: Optional[str] = None
    related_entities: list[str] = Field(default_factory=list)
    related: list[MilestoneLink] = Field(default_factory=list)
    importance_score: int = Field(ge=1, le=10, default=5)
    tags: list[str] = Field(default_factory=list)


class TimelineResponse(BaseModel):
    user_id: str
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    milestones: list[Milestone] = Field(default_factory=list)


# ── Search ──────────────────────────────────────────────────────────────

class SearchQuery(BaseModel):
    query: str
    user_id: str = "default"
    top_k: int = 10
    category: Optional[EntityCategory] = None


class SearchResult(BaseModel):
    id: str
    text: str
    score: float
    metadata: dict = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult] = Field(default_factory=list)
    answer: Optional[str] = None         # RAG-generated answer


# ── Phase 4: Advanced Retrieval Schemas ─────────────────────────────────

class SourceAttribution(BaseModel):
    """Source reference appended to RAG answers."""
    chunk_id: str
    source_file: str
    collection: str
    score: float
    snippet: str = ""                    # first 200 chars of chunk
    file_id: Optional[str] = None


class RetrievedChunk(BaseModel):
    """A single retrieved chunk with full provenance."""
    id: str
    text: str
    semantic_score: float = 0.0          # cosine similarity
    keyword_score: float = 0.0           # BM25 score
    combined_score: float = 0.0          # fused score
    metadata: dict = Field(default_factory=dict)
    source: SourceAttribution | None = None


class SourceDocument(BaseModel):
    """
    An original ingested document, as opposed to the facts extracted from it.

    Module 1's promise is that originals stay untouched and retrievable, so
    document-level queries ("show my latest resume") resolve to one of these and
    the client fetches the real file from ``/api/files/{file_id}``.
    """
    file_id: str = ""
    source_file: str = ""                # original filename, or the ingested URL
    file_type: str = ""
    chunk_count: int = 0
    uploaded_at: Optional[str] = None    # ISO timestamp, from the stored file
    entity_count: int = 0                # entities extracted from this document

    @computed_field  # type: ignore[prop-decorator]
    @property
    def download_url(self) -> str:
        """
        Where the original file can be fetched from.

        A computed field rather than a plain property so it is present in the
        serialised response — the frontend needs the link, and a bare property is
        invisible to ``model_dump``.
        """
        return f"/api/files/{self.file_id}" if self.file_id else ""


class DocumentListResponse(BaseModel):
    """Response for document-level retrieval."""
    user_id: str
    query: str = ""
    intent: str = ""                     # what the router read from the query
    total: int = 0
    documents: list[SourceDocument] = Field(default_factory=list)


class RAGQueryRequest(BaseModel):
    """POST body for /api/search/query — NL question with filters."""
    query: str
    user_id: str = "default"
    top_k: int = Field(10, ge=1, le=50)
    category: Optional[EntityCategory] = None
    date_from: Optional[str] = None      # YYYY-MM
    date_to: Optional[str] = None        # YYYY-MM
    tags: list[str] = Field(default_factory=list)
    use_mmr: bool = True                 # enable MMR reranking
    mmr_lambda: float = Field(0.7, ge=0.0, le=1.0)
    stream: bool = False                 # enable SSE streaming


class RAGAnswerResponse(BaseModel):
    """Full RAG answer with source citations."""
    query: str
    answer: str
    sources: list[SourceAttribution] = Field(default_factory=list)
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    retrieval_method: str = "hybrid"     # "semantic" | "keyword" | "hybrid"
    # What the query router read from the question, e.g.
    # "categories=certification" or "documents:resume latest". "none" means the
    # search ran unrestricted. Exposed so the UI can show why these results came
    # back, and so a wrong reading is visible instead of silent.
    intent: str = "none"
    # Populated only for document-level questions ("show my latest resume").
    documents: list[SourceDocument] = Field(default_factory=list)


class FacetedSearchRequest(BaseModel):
    """POST body for /api/search/filter — structured faceted search."""
    user_id: str = "default"
    categories: list[EntityCategory] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    min_importance: int = Field(1, ge=1, le=10)
    query: Optional[str] = None          # optional semantic component
    top_k: int = Field(20, ge=1, le=100)


class FacetedSearchResponse(BaseModel):
    """Response for structured faceted search."""
    filters_applied: dict = Field(default_factory=dict)
    total_results: int = 0
    results: list[RetrievedChunk] = Field(default_factory=list)


class SimilarEntityResponse(BaseModel):
    """Response for finding entities similar to a given one."""
    entity_id: str
    entity_title: str = ""
    similar: list[RetrievedChunk] = Field(default_factory=list)


# ── Relationship Engine ─────────────────────────────────────────────────

class RelationEvidence(BaseModel):
    """
    One concrete reason two entities are connected.

    This is what makes the knowledge map explainable rather than an opaque
    "nearest vector neighbour" list — every edge can show its receipts.
    """
    kind: str                            # shared_tag | tech_match | name_match
                                         # | temporal | mentioned_in | semantic
                                         # | career_signal
    detail: str                          # human-readable, e.g. "Both tagged 'Python'"
    weight: float = 0.0                  # contribution to the edge confidence

    @field_validator("weight")
    @classmethod
    def _round_weight(cls, v: float) -> float:
        """
        Weights are built up from float arithmetic like ``0.2 + 0.1 * n``, which
        surfaced "+0.30000000000000004" in the API response. Rounding here fixes
        it for every producer instead of at each of the ~30 call sites.
        """
        return round(v, 3)


class EntityRelation(BaseModel):
    """A single explainable edge in the knowledge graph."""
    source_id: str
    source_title: str
    source_category: str
    target_id: str
    target_title: str
    target_category: str
    relation_type: str                   # certifies | used_in | applied_at | led_to …
    label: str                           # sentence a reviewer can read
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    evidence: list[RelationEvidence] = Field(default_factory=list)


class GraphNode(BaseModel):
    """A node in the knowledge graph (an entity, or a derived career path)."""
    id: str
    title: str
    category: str                        # EntityCategory value, or "career_path"
    date: Optional[str] = None
    importance_score: int = 5
    tags: list[str] = Field(default_factory=list)
    file_id: Optional[str] = None
    degree: int = 0                      # number of edges touching this node


class KnowledgeGraphResponse(BaseModel):
    """The full explainable knowledge map for a user."""
    user_id: str
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[EntityRelation] = Field(default_factory=list)
    # Edge counts per relation_type — drives the legend in the UI.
    relation_counts: dict[str, int] = Field(default_factory=dict)
    career_paths: list[str] = Field(default_factory=list)


class EntityConnectionsResponse(BaseModel):
    """Explainable connections for one entity — powers the 'why?' panel."""
    entity_id: str
    entity_title: str
    entity_category: str
    connections: list[EntityRelation] = Field(default_factory=list)


# ── Identity / User ────────────────────────────────────────────────────

class UserProfile(BaseModel):
    user_id: str = "default"
    name: Optional[str] = None
    summary: Optional[str] = None
    top_skills: list[str] = Field(default_factory=list)
    total_entities: int = 0
    # Entity count per EntityCategory value ("skill", "project", …). Always
    # carries every category, using 0 for the ones the user has no records in.
    category_counts: dict[str, int] = Field(default_factory=dict)
