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

/**
 * A readable pointer from one milestone to a connected entity.
 * Carries the target's title and the reason for the edge, so the UI can
 * render a connection without a second request per milestone.
 */
export interface MilestoneLink {
  id: string;
  title: string;
  category: string;
  relation_type: string;
  /** Human-readable edge label, e.g. "Skill applied in a project". */
  label: string;
  /** Concrete evidence for the edge, "; "-joined. */
  why: string;
  confidence: number;
  /** "out" when this milestone is the source of the relation. */
  direction: string;
}

export interface Milestone {
  id: string;
  date: string | null;
  category: EntityCategory;
  title: string;
  description: string | null;
  /** Bare target IDs — kept for backwards compatibility; prefer `related`. */
  related_entities: string[];
  /** Explainable connections, highest confidence first. */
  related?: MilestoneLink[];
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
  /** What the query router read from the question, e.g. "categories=certification". */
  intent?: string;
  /** Original files matching a document-level question. */
  documents?: SourceDocument[];
}

/** An original ingested document, as opposed to the facts extracted from it. */
export interface SourceDocument {
  file_id: string;
  /** Original filename, or the ingested URL for a link. */
  source_file: string;
  file_type: string;
  chunk_count: number;
  uploaded_at: string | null;
  entity_count: number;
  /** `/api/files/{file_id}`, or "" for link ingests with no stored file. */
  download_url: string;
}

export interface DocumentListResponse {
  user_id: string;
  query: string;
  intent: string;
  total: number;
  documents: SourceDocument[];
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

// ── Relationship Engine ────────────────────────────────────────────────

/** One concrete reason two entities are connected — the edge's receipts. */
export interface RelationEvidence {
  /** shared_tag | tech_match | name_match | temporal | mentioned_in | semantic | career_signal */
  kind: string;
  /** Human-readable, e.g. "Both tagged 'Python'". */
  detail: string;
  /** Contribution to the edge confidence. */
  weight: number;
}

/** A single explainable edge in the knowledge graph. */
export interface EntityRelation {
  source_id: string;
  source_title: string;
  source_category: string;
  target_id: string;
  target_title: string;
  target_category: string;
  /** certifies | used_in | applied_at | leads_to | developed | … */
  relation_type: string;
  /** A sentence a reviewer can read. */
  label: string;
  confidence: number;
  evidence: RelationEvidence[];
}

export interface GraphNode {
  id: string;
  title: string;
  /** An EntityCategory value, or "career_path" for a derived node. */
  category: string;
  date: string | null;
  importance_score: number;
  tags: string[];
  file_id: string | null;
  /** Number of edges touching this node. */
  degree: number;
}

export interface KnowledgeGraphResponse {
  user_id: string;
  generated_at: string;
  nodes: GraphNode[];
  edges: EntityRelation[];
  /** Edge counts per relation_type — drives the legend. */
  relation_counts: Record<string, number>;
  career_paths: string[];
}

export interface EntityConnectionsResponse {
  entity_id: string;
  entity_title: string;
  entity_category: string;
  connections: EntityRelation[];
}

// ── Identity ───────────────────────────────────────────────────────────

export interface UserProfile {
  user_id: string;
  name: string | null;
  summary: string | null;
  top_skills: string[];
  total_entities: number;
  /** Entity count per category. Optional so older backends stay compatible. */
  category_counts?: Partial<Record<EntityCategory, number>>;
}
