"""
Pydantic schemas — request / response models for the API layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


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

class Milestone(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    date: Optional[str] = None           # YYYY-MM or free text
    category: EntityCategory
    title: str
    description: Optional[str] = None
    related_entities: list[str] = Field(default_factory=list)
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


# ── Identity / User ────────────────────────────────────────────────────

class UserProfile(BaseModel):
    user_id: str = "default"
    name: Optional[str] = None
    summary: Optional[str] = None
    top_skills: list[str] = Field(default_factory=list)
    total_entities: int = 0
