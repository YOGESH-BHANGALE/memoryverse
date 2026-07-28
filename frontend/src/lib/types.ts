/**
 * MemoryVerse AI — TypeScript type definitions.
 * Mirrors the backend Pydantic schemas.
 */

// ── Enums ──────────────────────────────────────────────────────────────

export type EntityCategory =
  | "skill"
  | "project"
  | "certification"
  | "internship"
  | "achievement"
  | "academics";

export type JobStatus = "pending" | "processing" | "completed" | "failed";

// ── Entities ───────────────────────────────────────────────────────────

export interface CategorisedEntity {
  id: string;
  category: EntityCategory;
  title: string;
  data: Record<string, any>;
  importance_score: number;
  tags: string[];
  date: string | null;
}

// ── Ingestion ──────────────────────────────────────────────────────────

export interface IngestionResult {
  job_id: string;
  status: JobStatus;
  filename: string;
  entities_extracted: number;
  entities: CategorisedEntity[];
  errors: string[];
}

export interface IngestionStatus {
  job_id: string;
  status: JobStatus;
  progress: string | null;
}

// ── Timeline ───────────────────────────────────────────────────────────

export interface Milestone {
  id: string;
  date: string | null;
  category: EntityCategory;
  title: string;
  description: string | null;
  related_entities: string[];
  importance_score: number;
  tags: string[];
}

export interface TimelineResponse {
  user_id: string;
  generated_at: string;
  milestones: Milestone[];
}

// ── Search ─────────────────────────────────────────────────────────────

export interface SearchResult {
  id: string;
  text: string;
  score: number;
  metadata: Record<string, any>;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  answer: string | null;
}

// ── Phase 4: Advanced Search Types ─────────────────────────────────────

export interface SourceAttribution {
  chunk_id: string;
  source_file: string;
  collection: string;
  score: number;
  snippet: string;
  file_id?: string;
}

export interface RetrievedChunk {
  id: string;
  text: string;
  semantic_score: number;
  keyword_score: number;
  combined_score: number;
  metadata: Record<string, any>;
  source: SourceAttribution | null;
}

export interface RAGQueryRequest {
  query: string;
  user_id?: string;
  top_k?: number;
  category?: EntityCategory;
  date_from?: string;
  date_to?: string;
  tags?: string[];
  use_mmr?: boolean;
  mmr_lambda?: number;
  stream?: boolean;
}

export interface RAGAnswerResponse {
  query: string;
  answer: string;
  sources: SourceAttribution[];
  chunks: RetrievedChunk[];
  retrieval_method: string;
}

export interface FacetedSearchRequest {
  user_id?: string;
  categories?: EntityCategory[];
  tags?: string[];
  date_from?: string;
  date_to?: string;
  min_importance?: number;
  query?: string;
  top_k?: number;
}

export interface FacetedSearchResponse {
  filters_applied: Record<string, any>;
  total_results: number;
  results: RetrievedChunk[];
}

export interface SimilarEntityResponse {
  entity_id: string;
  entity_title: string;
  similar: RetrievedChunk[];
}

// ── Identity ───────────────────────────────────────────────────────────

export interface UserProfile {
  user_id: string;
  name: string | null;
  summary: string | null;
  top_skills: string[];
  total_entities: number;
}
