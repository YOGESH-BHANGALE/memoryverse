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

// ── Resilient request wrapper ────────────────────────────────────────────

/**
 * Transient failures worth retrying against the free-tier backend:
 *  - It spins down after ~15 min idle; the first request wakes it (a ~30-60s
 *    cold start) and can time out or briefly 502 before uvicorn is listening.
 *  - A worker restart window returns 502/503 for a few seconds.
 * All clear on their own, so a short backoff turns them into a seamless wait
 * instead of a hard error the user sees.
 */
const RETRYABLE_STATUS = new Set([502, 503, 504]);
const RETRY_DELAYS_MS = [3_000, 8_000, 15_000];

function isRetryable(err: any): boolean {
  // No `response` means the request never got an HTTP reply — network error or
  // a timeout (axios sets code "ECONNABORTED"), both typical of a cold start.
  if (!err?.response) return true;
  return RETRYABLE_STATUS.has(err.response.status);
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Fired before each backoff wait so callers can explain the pause. */
export type RetryNotice = (attempt: number, waitMs: number) => void;

/**
 * Run `fn`, retrying transient free-tier failures with a fixed backoff.
 *
 * Safe for uploads specifically because ingestion is idempotent: chunk and
 * entity IDs are deterministic, so a re-run upserts over the same rows rather
 * than duplicating them. And on Render a 502/503 means the worker died before
 * responding — the pipeline did not complete — so there is nothing to undo.
 */
async function withRetry<T>(fn: () => Promise<T>, onRetry?: RetryNotice): Promise<T> {
  let lastErr: any;
  for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastErr = err;
      if (attempt >= RETRY_DELAYS_MS.length || !isRetryable(err)) throw err;
      const waitMs = RETRY_DELAYS_MS[attempt];
      onRetry?.(attempt + 1, waitMs);
      await sleep(waitMs);
    }
  }
  throw lastErr;
}

// ── Ingestion ──────────────────────────────────────────────────────────

export async function uploadFile(
  file: File,
  userId: string = getOrCreateUserId(),
  onRetry?: RetryNotice
): Promise<IngestionResult> {
  const formData = new FormData();
  formData.append("file", file);
  return withRetry(async () => {
    const { data } = await client.post<IngestionResult>(
      `/api/ingest/upload?user_id=${encodeURIComponent(userId)}`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
    return data;
  }, onRetry);
}

export async function uploadLink(
  url: string,
  userId: string = getOrCreateUserId(),
  onRetry?: RetryNotice
): Promise<IngestionResult> {
  return withRetry(async () => {
    const { data } = await client.post<IngestionResult>(
      `/api/ingest/link?user_id=${encodeURIComponent(userId)}`,
      { url },
      { headers: { "Content-Type": "application/json" } }
    );
    return data;
  }, onRetry);
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
