"use client";

import React, { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { KnowledgeMap } from "@/components/graph/KnowledgeMap";
import { getKnowledgeGraph, rebuildKnowledgeGraph } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import type { KnowledgeGraphResponse } from "@/lib/types";

export default function GraphPage() {
  const userId = useAppStore((s) => s.userId);
  const [graph, setGraph] = useState<KnowledgeGraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [rebuilding, setRebuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setGraph(await getKnowledgeGraph(userId));
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
          err?.message ||
          "Could not load the knowledge graph"
      );
      setGraph(null);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleRebuild = async () => {
    setRebuilding(true);
    setError(null);
    try {
      // Recomputes edges across every document and writes them back into entity
      // metadata — needed for corpora ingested before the relation engine.
      setGraph(await rebuildKnowledgeGraph(userId));
    } catch (err: any) {
      setError(
        err?.response?.data?.detail || err?.message || "Rebuild failed"
      );
    } finally {
      setRebuilding(false);
    }
  };

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start justify-between gap-4 flex-wrap"
      >
        <div>
          <h1 className="text-3xl font-bold text-white">Knowledge Map</h1>
          <p className="text-dark-200 mt-1">
            How your certifications, skills, projects and internships connect —
            and the evidence behind every link
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleRebuild}
            disabled={rebuilding || loading}
          >
            {rebuilding ? "Rebuilding…" : "↻ Rebuild graph"}
          </Button>
        </div>
      </motion.div>

      {loading && (
        <Card className="text-center py-16">
          <div className="w-6 h-6 mx-auto border-2 border-primary-400 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-dark-300 mt-3">Mapping your knowledge…</p>
        </Card>
      )}

      {!loading && error && (
        <Card className="border-amber-500/30 bg-amber-500/5 text-center py-12">
          <p className="text-4xl mb-3">🕸️</p>
          <p className="text-sm text-amber-300">{error}</p>
          <p className="text-xs text-dark-300 mt-2">
            Upload a resume, a certificate and a project report — the map builds
            itself from there.
          </p>
        </Card>
      )}

      {!loading && !error && graph && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <KnowledgeMap graph={graph} />
        </motion.div>
      )}
    </div>
  );
}
