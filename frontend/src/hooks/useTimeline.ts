"use client";

import { useState, useEffect, useCallback } from "react";
import { getTimeline } from "@/lib/api";
import type { TimelineResponse, Milestone } from "@/lib/types";

export function useTimeline(userId: string = "default") {
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(
    async (year?: string, category?: string) => {
      setLoading(true);
      setError(null);
      try {
        const result = await getTimeline(userId, year, category);
        setData(result);
      } catch (err: any) {
        setError(err?.response?.data?.detail || err.message || "Failed to load timeline");
      } finally {
        setLoading(false);
      }
    },
    [userId]
  );

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { data, loading, error, refetch: fetch };
}
