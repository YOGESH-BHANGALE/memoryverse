"use client";

import { useState, useCallback, useRef } from "react";
import { ragQuery, ragQueryStream } from "@/lib/api";
import type {
  RAGAnswerResponse,
  RAGQueryRequest,
  SourceAttribution,
} from "@/lib/types";

export function useSearch(userId: string = "default") {
  const [data, setData] = useState<RAGAnswerResponse | null>(null);
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [streamingSources, setStreamingSources] = useState<SourceAttribution[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef(false);

  /**
   * Non-streaming search — returns full answer at once.
   */
  const search = useCallback(
    async (query: string, category?: string) => {
      if (!query.trim()) return;
      setLoading(true);
      setError(null);
      setData(null);
      setStreamingAnswer("");
      setStreamingSources([]);
      try {
        const request: RAGQueryRequest = {
          query,
          user_id: userId,
          top_k: 10,
          category: category as any,
          use_mmr: true,
        };
        const result = await ragQuery(request);
        setData(result);
      } catch (err: any) {
        setError(err?.response?.data?.detail || err.message || "Search failed");
      } finally {
        setLoading(false);
      }
    },
    [userId]
  );

  /**
   * Streaming search — answer tokens arrive incrementally via SSE.
   */
  const searchStream = useCallback(
    async (query: string, category?: string) => {
      if (!query.trim()) return;
      setLoading(true);
      setIsStreaming(true);
      setError(null);
      setData(null);
      setStreamingAnswer("");
      setStreamingSources([]);
      abortRef.current = false;

      try {
        const request: RAGQueryRequest = {
          query,
          user_id: userId,
          top_k: 10,
          category: category as any,
          use_mmr: true,
          stream: true,
        };

        await ragQueryStream(request, {
          onChunk: (token) => {
            if (!abortRef.current) {
              setStreamingAnswer((prev) => prev + token);
            }
          },
          onSources: (sources) => {
            setStreamingSources(sources);
          },
          onDone: () => {
            setIsStreaming(false);
            setLoading(false);
          },
          onError: (errMsg) => {
            setError(errMsg);
            setIsStreaming(false);
            setLoading(false);
          },
        });
      } catch (err: any) {
        setError(err.message || "Streaming search failed");
        setIsStreaming(false);
        setLoading(false);
      }
    },
    [userId]
  );

  const clear = useCallback(() => {
    abortRef.current = true;
    setData(null);
    setStreamingAnswer("");
    setStreamingSources([]);
    setError(null);
    setIsStreaming(false);
  }, []);

  return {
    data,
    streamingAnswer,
    streamingSources,
    isStreaming,
    loading,
    error,
    search,
    searchStream,
    clear,
  };
}
