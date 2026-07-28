/**
 * MemoryVerse AI — API client.
 * Wraps all backend endpoints with typed methods.
 */

import axios from "axios";
import type {
  IngestionResult,
  IngestionStatus,
  TimelineResponse,
  SearchResponse,
  UserProfile,
  RAGQueryRequest,
  RAGAnswerResponse,
  SourceAttribution,
  FacetedSearchRequest,
  FacetedSearchResponse,
  SimilarEntityResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const client = axios.create({
  baseURL: API_BASE,
  timeout: 120_000, // 2 minutes for large uploads
});

// ── Ingestion ──────────────────────────────────────────────────────────

export async function uploadFile(
  file: File,
  userId: string = "default"
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
  userId: string = "default"
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

export async function getTimeline(
  userId: string = "default",
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
  userId: string = "default",
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
    { ...request, stream: false }
  );
  return data;
}

/**
 * SSE streaming RAG query.
 * Returns an EventSource-like reader that calls onChunk for tokens
 * and onSources for the final source citations.
 */
export async function ragQueryStream(
  request: RAGQueryRequest,
  callbacks: {
    onChunk: (token: string) => void;
    onSources: (sources: SourceAttribution[]) => void;
    onDone: () => void;
    onError?: (err: string) => void;
  }
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/search/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...request, stream: true }),
  });

  if (!response.ok || !response.body) {
    callbacks.onError?.(`Request failed: ${response.statusText}`);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    let currentEvent = "";
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        const data = line.slice(6);
        switch (currentEvent) {
          case "chunk":
            callbacks.onChunk(data);
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
      }
    }
  }
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
    request
  );
  return data;
}

// ── Identity ───────────────────────────────────────────────────────────

export async function getUserProfile(
  userId: string = "default"
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
  getUserProfile,
};
