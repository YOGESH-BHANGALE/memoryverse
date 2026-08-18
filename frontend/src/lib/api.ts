/**
 * MemoryVerse AI — API client.
 * Wraps all backend endpoints with typed methods.
 */

import axios from "axios";
import { getOrCreateUserId } from "./user";
import type {
  IngestionResult,
  IngestionStatus,
  TimelineResponse,
  SearchResponse,
  UserProfile,
  RAGQueryRequest,
  RAGAnswerResponse,
  SourceAttribution,
  SourceDocument,
  DocumentListResponse,
  FacetedSearchRequest,
  FacetedSearchResponse,
  SimilarEntityResponse,
  KnowledgeGraphResponse,
  EntityConnectionsResponse,
} from "./types";

const LIVE_BACKEND_URL = "https://memoryverse-backend-bju3.onrender.com";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (typeof window !== "undefined" && window.location.hostname === "localhost"
    ? "http://localhost:8000"
    : LIVE_BACKEND_URL);

const client = axios.create({
  baseURL: API_BASE,
  timeout: 120_000, // 2 minutes for large uploads
});

// ── Ingestion ──────────────────────────────────────────────────────────

export async function uploadFile(
  file: File,
  userId: string = getOrCreateUserId()
): Promise<IngestionResult> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await client.post<IngestionResult>(
    `/api/ingest/upload?user_id=${encodeURIComponent(userId)}`,
    formData,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data;
}

export async function uploadLink(
  url: string,
  userId: string = getOrCreateUserId()
): Promise<IngestionResult> {
  const { data } = await client.post<IngestionResult>(
    `/api/ingest/link?user_id=${encodeURIComponent(userId)}`,
    { url },
    { headers: { "Content-Type": "application/json" } }
  );
  return data;
}

export async function getIngestionStatus(
  jobId: string
): Promise<IngestionStatus> {
  const { data } = await client.get<IngestionStatus>(
    `/api/ingest/status/${jobId}`
  );
  return data;
}

// ── Timeline ───────────────────────────────────────────────────────────

// ── Timeline ───────────────────────────────────────────────────────────

export async function getTimeline(
  userId: string = getOrCreateUserId(),
  year?: string,
  category?: string
): Promise<TimelineResponse> {
  const params = new URLSearchParams();
  if (year) params.set("year", year);
  if (category) params.set("category", category);
  const qs = params.toString();
  const { data } = await client.get<TimelineResponse>(
    `/api/timeline/${userId}${qs ? `?${qs}` : ""}`
  );
  return data;
}

// ── Search (legacy) ────────────────────────────────────────────────────

export async function searchQuery(
  query: string,
  userId: string = getOrCreateUserId(),
  topK: number = 10,
  category?: string
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, user_id: userId, top_k: String(topK) });
  if (category) params.set("category", category);
  const { data } = await client.get<SearchResponse>(`/api/search/?${params}`);
  return data;
}

// ── Phase 4: Advanced Search ───────────────────────────────────────────

export async function ragQuery(
  request: RAGQueryRequest
): Promise<RAGAnswerResponse> {
  const { data } = await client.post<RAGAnswerResponse>(
    "/api/search/query",
    { user_id: getOrCreateUserId(), ...request, stream: false }
  );
  return data;
}

/**
 * SSE streaming RAG query.
 * Returns an EventSource-like reader that calls onChunk for tokens
 * and onSources for the final source citations.
 *
 * `onIntent` and `onDocuments` fire before the answer tokens: the router's
 * reading of the query and any matching original files are known up front, so
 * the UI can show download links without waiting for generation to finish.
 */
export async function ragQueryStream(
  request: RAGQueryRequest,
  callbacks: {
    onChunk: (token: string) => void;
    onSources: (sources: SourceAttribution[]) => void;
    onDone: () => void;
    onError?: (err: string) => void;
    onIntent?: (intent: string) => void;
    onDocuments?: (documents: SourceDocument[]) => void;
  }
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/search/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: getOrCreateUserId(), ...request, stream: true }),
  });

  if (!response.ok || !response.body) {
    callbacks.onError?.(`Request failed: ${response.statusText}`);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // Parse one complete SSE event block ("event:" + one or more "data:" lines).
  // Multi-line payloads arrive as consecutive "data:" fields and must be
  // rejoined with "\n", otherwise newlines and bullet lists are lost.
  const handleEvent = (raw: string) => {
    let eventName = "";
    const dataLines: string[] = [];

    for (const rawLine of raw.split("\n")) {
      const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
      if (line.startsWith(":")) continue; // comment / keep-alive
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const value = line.slice(5);
        dataLines.push(value.startsWith(" ") ? value.slice(1) : value);
      }
    }

    const data = dataLines.join("\n");
    switch (eventName) {
      case "chunk":
        callbacks.onChunk(data);
        break;
      case "intent":
        callbacks.onIntent?.(data);
        break;
      case "documents":
        try {
          callbacks.onDocuments?.(JSON.parse(data) as SourceDocument[]);
        } catch {}
        break;
      case "sources":
        try {
          const sources = JSON.parse(data) as SourceAttribution[];
          callbacks.onSources(sources);
        } catch {}
        break;
      case "done":
        callbacks.onDone();
        break;
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Events are separated by a blank line. Only dispatch complete blocks so
    // an "event:"/"data:" pair split across network reads stays intact.
    let sep = buffer.indexOf("\n\n");
    while (sep !== -1) {
      const rawEvent = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      if (rawEvent.trim()) handleEvent(rawEvent);
      sep = buffer.indexOf("\n\n");
    }
  }

  // Flush a trailing event that was not terminated by a blank line.
  buffer += decoder.decode();
  if (buffer.trim()) handleEvent(buffer);
}

export async function findSimilar(
  entityId: string,
  topK: number = 10
): Promise<SimilarEntityResponse> {
  const { data } = await client.get<SimilarEntityResponse>(
    `/api/search/similar/${entityId}?top_k=${topK}`
  );
  return data;
}

export async function facetedSearch(
  request: FacetedSearchRequest
): Promise<FacetedSearchResponse> {
  const { data } = await client.post<FacetedSearchResponse>(
    "/api/search/filter",
    { user_id: getOrCreateUserId(), ...request }
  );
  return data;
}

// ── Relationship Engine ────────────────────────────────────────────────

/**
 * Fetch the explainable knowledge map: nodes, edges, and the evidence behind
 * each edge. `min_confidence` drops weak connections server-side.
 */
export async function getKnowledgeGraph(
  userId: string = getOrCreateUserId(),
  minConfidence?: number
): Promise<KnowledgeGraphResponse> {
  const qs = minConfidence != null ? `?min_confidence=${minConfidence}` : "";
  const { data } = await client.get<KnowledgeGraphResponse>(
    `/api/relations/graph/${userId}${qs}`
  );
  return data;
}

/**
 * Connections for one entity, each with the reason it exists.
 * Prefer this over `findSimilar`, which is raw vector similarity with no
 * explanation attached.
 */
export async function getEntityConnections(
  entityId: string,
  userId: string = getOrCreateUserId()
): Promise<EntityConnectionsResponse> {
  const { data } = await client.get<EntityConnectionsResponse>(
    `/api/relations/entity/${entityId}?user_id=${encodeURIComponent(userId)}`
  );
  return data;
}

export async function rebuildKnowledgeGraph(
  userId: string = getOrCreateUserId()
): Promise<KnowledgeGraphResponse> {
  const { data } = await client.post<KnowledgeGraphResponse>(
    `/api/relations/rebuild/${userId}`
  );
  return data;
}

// ── Original Documents ─────────────────────────────────────────────────

/**
 * List the original ingested files, newest first. An optional natural-language
 * query narrows by document type and recency ("show my latest resume").
 */
export async function listDocuments(
  query: string = "",
  userId: string = getOrCreateUserId(),
  limit: number = 20
): Promise<DocumentListResponse> {
  const params = new URLSearchParams({ user_id: userId, limit: String(limit) });
  if (query) params.set("q", query);
  const { data } = await client.get<DocumentListResponse>(
    `/api/search/documents?${params}`
  );
  return data;
}

/**
 * Absolute URL for an original file, in its original format.
 *
 * Backend responses carry a root-relative `download_url`, which breaks when the
 * frontend and API are on different origins (the deployed setup), so resolve it
 * against API_BASE here rather than in each component.
 */
export function fileUrl(fileIdOrPath?: string | null): string {
  if (!fileIdOrPath) return "";
  return fileIdOrPath.startsWith("/")
    ? `${API_BASE}${fileIdOrPath}`
    : `${API_BASE}/api/files/${fileIdOrPath}`;
}

// ── Identity ───────────────────────────────────────────────────────────

export async function getUserProfile(
  userId: string = getOrCreateUserId()
): Promise<UserProfile> {
  const { data } = await client.get<UserProfile>(`/api/identity/${userId}`);
  return data;
}

export const api = {
  uploadFile,
  uploadLink,
  getIngestionStatus,
  getTimeline,
  searchQuery,
  ragQuery,
  ragQueryStream,
  findSimilar,
  facetedSearch,
  getKnowledgeGraph,
  getEntityConnections,
  rebuildKnowledgeGraph,
  listDocuments,
  fileUrl,
  getUserProfile,
};
