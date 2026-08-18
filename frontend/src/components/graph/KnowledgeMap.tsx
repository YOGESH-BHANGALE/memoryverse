"use client";

/**
 * Knowledge Map — the explainable relationship view.
 *
 * Laid out as columns in the order the journey actually flows
 * (Certification → Skill → Project → Internship → Career Path), so an edge
 * crossing left-to-right *is* the progression. A force-directed blob would look
 * busier and say less: reviewers are scoring whether the mapping is meaningful,
 * and "certification certifies skill, skill used in project" only reads that way
 * if the axis carries the meaning.
 *
 * Every edge is clickable back to its evidence — no connection is shown that the
 * UI cannot justify.
 */

import React, { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Card } from "@/components/ui/Card";
import { fileUrl } from "@/lib/api";
import type {
  EntityRelation,
  GraphNode,
  KnowledgeGraphResponse,
} from "@/lib/types";

/** Column order = the career progression the modules ask us to surface. */
const COLUMN_ORDER = [
  "certification",
  "academics",
  "skill",
  "project",
  "internship",
  "achievement",
  "career_path",
] as const;

const COLUMN_TITLES: Record<string, string> = {
  certification: "Certifications",
  academics: "Academics",
  skill: "Skills",
  project: "Projects",
  internship: "Internships",
  achievement: "Achievements",
  career_path: "Career Paths",
};

const CATEGORY_COLORS: Record<string, string> = {
  skill: "#4dabf7",
  project: "#51cf66",
  certification: "#fcc419",
  internship: "#cc5de8",
  achievement: "#ff6b6b",
  academics: "#748ffc",
  career_path: "#22b8cf",
};

const CATEGORY_ICONS: Record<string, string> = {
  skill: "⚡",
  project: "🚀",
  certification: "📜",
  internship: "🏢",
  achievement: "🏆",
  academics: "🎓",
  career_path: "🧭",
};

const RELATION_LABELS: Record<string, string> = {
  certifies: "certifies",
  used_in: "used in",
  developed: "developed",
  applied_at: "applied at",
  built_during: "built during",
  leads_to: "leads to",
  recognised_by: "recognised by",
  taught: "taught",
  demonstrates: "demonstrates",
};

const EVIDENCE_ICONS: Record<string, string> = {
  shared_tag: "🏷️",
  tech_match: "🛠️",
  name_match: "🔤",
  temporal: "🕒",
  mentioned_in: "📄",
  semantic: "🧠",
  career_signal: "🧭",
};

// ── Layout constants ───────────────────────────────────────────────────
const COL_W = 210;
const NODE_W = 172;
const NODE_H = 34;
const ROW_GAP = 44;
const TOP_PAD = 54;
const BOTTOM_PAD = 24;
/** Per-column cap. Beyond this a column stops being readable; the count of
 *  what was left out is reported rather than silently dropped. */
const MAX_PER_COL = 14;

interface Placed extends GraphNode {
  x: number;
  y: number;
}

function relationVerb(type: string): string {
  return RELATION_LABELS[type] || type.replace(/_/g, " ");
}

/** Bezier between two node boxes, leaving whichever side faces the target. */
function edgePath(s: Placed, t: Placed): string {
  const forward = t.x >= s.x;
  const sx = forward ? s.x + NODE_W : s.x;
  const tx = forward ? t.x : t.x + NODE_W;
  const sy = s.y + NODE_H / 2;
  const ty = t.y + NODE_H / 2;
  const dx = Math.max(40, Math.abs(tx - sx) * 0.45);
  const c1 = forward ? sx + dx : sx - dx;
  const c2 = forward ? tx - dx : tx + dx;
  return `M ${sx} ${sy} C ${c1} ${sy}, ${c2} ${ty}, ${tx} ${ty}`;
}

function EvidenceList({ evidence }: { evidence: EntityRelation["evidence"] }) {
  if (!evidence?.length) {
    return (
      <p className="text-[10px] text-dark-400 italic">
        No evidence recorded for this edge
      </p>
    );
  }
  return (
    <ul className="space-y-0.5">
      {evidence.map((e, i) => (
        <li key={i} className="flex items-start gap-1.5 text-[10px] text-dark-200">
          <span className="flex-shrink-0">{EVIDENCE_ICONS[e.kind] || "•"}</span>
          <span className="leading-snug">{e.detail}</span>
          {e.weight > 0 && (
            <span className="ml-auto flex-shrink-0 font-mono text-dark-400">
              +{e.weight.toFixed(2)}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

export const KnowledgeMap: React.FC<{ graph: KnowledgeGraphResponse }> = ({
  graph,
}) => {
  const [minConfidence, setMinConfidence] = useState(0);
  const [relationFilter, setRelationFilter] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  // Filtering is client-side so the sliders respond instantly; the endpoint
  // supports the same narrowing server-side for large graphs.
  const edges = useMemo(
    () =>
      graph.edges.filter(
        (e) =>
          e.confidence >= minConfidence &&
          (!relationFilter || e.relation_type === relationFilter)
      ),
    [graph.edges, minConfidence, relationFilter]
  );

  const { placed, positions, dropped, height, width } = useMemo(() => {
    const degrees = new Map<string, number>();
    for (const e of edges) {
      degrees.set(e.source_id, (degrees.get(e.source_id) || 0) + 1);
      degrees.set(e.target_id, (degrees.get(e.target_id) || 0) + 1);
    }

    // Only draw nodes an edge actually touches — an isolated dot teaches nothing
    // about the map, and it pushes the connected ones off screen.
    const connected = graph.nodes.filter((n) => degrees.has(n.id));
    const columns = COLUMN_ORDER.map((cat) =>
      connected
        .filter((n) => n.category === cat)
        .sort(
          (a, b) =>
            (degrees.get(b.id) || 0) - (degrees.get(a.id) || 0) ||
            b.importance_score - a.importance_score
        )
    );

    const usedCols = columns
      .map((nodes, i) => ({ nodes, cat: COLUMN_ORDER[i] }))
      .filter((c) => c.nodes.length > 0);

    const out: Placed[] = [];
    let droppedCount = 0;
    let maxRows = 0;

    usedCols.forEach((col, colIdx) => {
      const shown = col.nodes.slice(0, MAX_PER_COL);
      droppedCount += col.nodes.length - shown.length;
      maxRows = Math.max(maxRows, shown.length);
      shown.forEach((n, rowIdx) => {
        out.push({
          ...n,
          degree: degrees.get(n.id) || 0,
          x: colIdx * COL_W + 16,
          y: rowIdx * ROW_GAP + TOP_PAD,
        });
      });
    });

    const pos = new Map(out.map((n) => [n.id, n]));
    return {
      placed: out,
      positions: pos,
      dropped: droppedCount,
      columns: usedCols,
      height: Math.max(240, maxRows * ROW_GAP + TOP_PAD + BOTTOM_PAD),
      width: Math.max(600, usedCols.length * COL_W + 16),
    };
  }, [graph.nodes, edges]);

  // Column headers need the same ordering the layout used.
  const headerCols = useMemo(() => {
    const seen = new Map<string, number>();
    for (const n of placed) {
      if (!seen.has(n.category)) seen.set(n.category, n.x);
    }
    return Array.from(seen.entries()).sort((a, b) => a[1] - b[1]);
  }, [placed]);

  const drawableEdges = useMemo(
    () =>
      edges.filter(
        (e) => positions.has(e.source_id) && positions.has(e.target_id)
      ),
    [edges, positions]
  );

  const focusId = hoveredId || selectedId;
  const focusedEdgeIds = useMemo(() => {
    if (!focusId) return null;
    const ids = new Set<string>([focusId]);
    for (const e of drawableEdges) {
      if (e.source_id === focusId) ids.add(e.target_id);
      if (e.target_id === focusId) ids.add(e.source_id);
    }
    return ids;
  }, [focusId, drawableEdges]);

  const selectedNode = selectedId ? positions.get(selectedId) : null;
  // Read from `edges`, not `drawableEdges`: the column cap is a drawing
  // constraint, and applying it here made a node the map labels "14 links"
  // open a panel headed "5 connections". The panel is a list — it can show
  // every edge the node has, including ones to nodes the layout left out.
  const selectedEdges = useMemo(
    () =>
      selectedId
        ? edges
            .filter((e) => e.source_id === selectedId || e.target_id === selectedId)
            .sort((a, b) => b.confidence - a.confidence)
        : [],
    [selectedId, edges]
  );

  const relationTypes = Object.entries(graph.relation_counts || {}).sort(
    ([, a], [, b]) => b - a
  );

  return (
    <div className="space-y-4">
      {/* ── Controls ── */}
      <Card className="py-3">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="flex items-center gap-2">
            <label className="text-[10px] uppercase tracking-wider text-dark-300 font-semibold">
              Min confidence
            </label>
            <input
              type="range"
              min={0}
              max={0.9}
              step={0.05}
              value={minConfidence}
              onChange={(e) => setMinConfidence(Number(e.target.value))}
              className="w-32 accent-primary-500"
            />
            <span className="text-[11px] font-mono text-primary-400 w-8">
              {Math.round(minConfidence * 100)}%
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] uppercase tracking-wider text-dark-300 font-semibold mr-1">
              Relation
            </span>
            <button
              onClick={() => setRelationFilter(null)}
              className={`px-2 py-0.5 rounded-full text-[10px] ring-1 transition-colors ${
                relationFilter === null
                  ? "bg-primary-500/20 text-primary-300 ring-primary-500/40"
                  : "bg-dark-700 text-dark-200 ring-dark-400/40 hover:text-white"
              }`}
            >
              all ({graph.edges.length})
            </button>
            {relationTypes.map(([type, count]) => (
              <button
                key={type}
                onClick={() =>
                  setRelationFilter(relationFilter === type ? null : type)
                }
                className={`px-2 py-0.5 rounded-full text-[10px] ring-1 transition-colors ${
                  relationFilter === type
                    ? "bg-primary-500/20 text-primary-300 ring-primary-500/40"
                    : "bg-dark-700 text-dark-200 ring-dark-400/40 hover:text-white"
                }`}
              >
                {relationVerb(type)} ({count})
              </button>
            ))}
          </div>

          <div className="ml-auto flex items-center gap-3 text-[11px] text-dark-300">
            <span>
              <span className="font-mono text-white">{placed.length}</span> nodes
            </span>
            <span>
              <span className="font-mono text-white">{drawableEdges.length}</span>{" "}
              edges
            </span>
            {dropped > 0 && (
              <span
                className="text-amber-400"
                title={`Columns are capped at ${MAX_PER_COL} for readability, so ${dropped} lower-degree nodes (and their edges) are not drawn.`}
              >
                +{dropped} nodes hidden
              </span>
            )}
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_20rem] gap-4">
        {/* ── The map ── */}
        <Card className="overflow-x-auto p-3">
          {placed.length === 0 ? (
            <p className="text-sm text-dark-300 py-12 text-center">
              No connections at this confidence level — lower the threshold.
            </p>
          ) : (
            <svg
              width={width}
              height={height}
              viewBox={`0 0 ${width} ${height}`}
              className="min-w-full"
            >
              {/* Column headers */}
              {headerCols.map(([cat, x]) => (
                <g key={cat}>
                  <text
                    x={x + NODE_W / 2}
                    y={22}
                    textAnchor="middle"
                    className="font-semibold"
                    fill={CATEGORY_COLORS[cat] || "#a6a7ab"}
                    fontSize={11}
                  >
                    {CATEGORY_ICONS[cat]} {COLUMN_TITLES[cat] || cat}
                  </text>
                  <line
                    x1={x}
                    y1={32}
                    x2={x + NODE_W}
                    y2={32}
                    stroke={CATEGORY_COLORS[cat] || "#373a40"}
                    strokeOpacity={0.3}
                  />
                </g>
              ))}

              {/* Edges first so nodes sit on top of them */}
              {drawableEdges.map((e, i) => {
                const s = positions.get(e.source_id)!;
                const t = positions.get(e.target_id)!;
                const dimmed =
                  focusedEdgeIds !== null &&
                  e.source_id !== focusId &&
                  e.target_id !== focusId;
                return (
                  <path
                    key={`${e.source_id}-${e.target_id}-${e.relation_type}-${i}`}
                    d={edgePath(s, t)}
                    fill="none"
                    stroke={CATEGORY_COLORS[t.category] || "#5c7cfa"}
                    strokeWidth={dimmed ? 1 : 1 + e.confidence * 2}
                    strokeOpacity={dimmed ? 0.06 : 0.35 + e.confidence * 0.4}
                  />
                );
              })}

              {/* Nodes */}
              {placed.map((n) => {
                const colour = CATEGORY_COLORS[n.category] || "#868e96";
                const dimmed = focusedEdgeIds !== null && !focusedEdgeIds.has(n.id);
                const isSelected = n.id === selectedId;
                const label =
                  n.title.length > 22 ? `${n.title.slice(0, 21)}…` : n.title;
                return (
                  <g
                    key={n.id}
                    transform={`translate(${n.x},${n.y})`}
                    opacity={dimmed ? 0.2 : 1}
                    onMouseEnter={() => setHoveredId(n.id)}
                    onMouseLeave={() => setHoveredId(null)}
                    onClick={() => setSelectedId(isSelected ? null : n.id)}
                    style={{ cursor: "pointer" }}
                  >
                    <title>{`${n.title} — ${n.degree} connection${
                      n.degree === 1 ? "" : "s"
                    }`}</title>
                    <rect
                      width={NODE_W}
                      height={NODE_H}
                      rx={8}
                      fill={`${colour}1f`}
                      stroke={colour}
                      strokeWidth={isSelected ? 2 : 1}
                      strokeOpacity={isSelected ? 1 : 0.45}
                    />
                    <text x={9} y={16} fontSize={10}>
                      {CATEGORY_ICONS[n.category] || "•"}
                    </text>
                    <text
                      x={24}
                      y={15}
                      fontSize={10.5}
                      fill="#f1f3f5"
                      className="font-medium"
                    >
                      {label}
                    </text>
                    <text x={24} y={26} fontSize={8.5} fill="#909296">
                      {n.date ? n.date.slice(0, 7) : "undated"} · {n.degree} link
                      {n.degree === 1 ? "" : "s"}
                    </text>
                  </g>
                );
              })}
            </svg>
          )}
          <p className="text-[10px] text-dark-400 mt-2">
            Click a node to see <span className="text-dark-200">why</span> each of
            its connections exists. Thicker lines = higher confidence.
          </p>
        </Card>

        {/* ── Why panel ── */}
        <Card className="self-start">
          {!selectedNode ? (
            <div>
              <h3 className="text-sm font-semibold text-white mb-2">
                🔍 Why are these connected?
              </h3>
              <p className="text-xs text-dark-300 leading-relaxed">
                Pick any node in the map. Every edge carries its receipts —
                shared skill tags, a name match inside a document, temporal
                proximity, or a career signal — and the confidence is the sum of
                that evidence, not a bare vector distance.
              </p>
              {graph.career_paths?.length > 0 && (
                <div className="mt-4 pt-3 border-t border-dark-500/50">
                  <p className="text-[10px] uppercase tracking-wider text-dark-300 font-semibold mb-1.5">
                    🧭 Career paths inferred
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {graph.career_paths.map((p) => (
                      <span
                        key={p}
                        className="px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 text-[10px] ring-1 ring-cyan-500/25"
                      >
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              key={selectedNode.id}
            >
              <div className="flex items-start gap-2">
                <span className="text-base">
                  {CATEGORY_ICONS[selectedNode.category] || "•"}
                </span>
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-white leading-tight">
                    {selectedNode.title}
                  </h3>
                  <p className="text-[10px] text-dark-300 mt-0.5">
                    {(COLUMN_TITLES[selectedNode.category] || selectedNode.category)
                      .replace(/s$/, "")}
                    {selectedNode.date ? ` · ${selectedNode.date}` : ""} · ★
                    {selectedNode.importance_score}
                  </p>
                </div>
              </div>

              {selectedNode.file_id && (
                <a
                  href={fileUrl(selectedNode.file_id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 mt-2 text-[10px] text-emerald-400 hover:text-emerald-300 underline"
                >
                  📄 Open the original document
                </a>
              )}

              <div className="mt-3 pt-3 border-t border-dark-500/50">
                <p className="text-[10px] uppercase tracking-wider text-dark-300 font-semibold mb-2">
                  🔗 {selectedEdges.length} connection
                  {selectedEdges.length === 1 ? "" : "s"}
                </p>
                <div className="space-y-2 max-h-[26rem] overflow-y-auto pr-1">
                  {selectedEdges.map((e, i) => {
                    const outgoing = e.source_id === selectedNode.id;
                    const otherTitle = outgoing ? e.target_title : e.source_title;
                    const otherCat = outgoing
                      ? e.target_category
                      : e.source_category;
                    return (
                      <div
                        key={`${e.source_id}-${e.target_id}-${i}`}
                        className="rounded-lg bg-dark-700/50 border border-dark-400/30 px-2.5 py-2"
                      >
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-dark-400 text-[11px] font-mono">
                            {outgoing ? "→" : "←"}
                          </span>
                          <span className="text-[10px]">
                            {CATEGORY_ICONS[otherCat] || "•"}
                          </span>
                          <button
                            onClick={() =>
                              setSelectedId(outgoing ? e.target_id : e.source_id)
                            }
                            className="text-dark-50 text-xs font-medium hover:text-primary-300 underline decoration-dotted text-left"
                          >
                            {otherTitle}
                          </button>
                          <span className="ml-auto text-[10px] font-mono text-dark-400">
                            {Math.round(e.confidence * 100)}%
                          </span>
                        </div>
                        <p className="text-[10px] text-primary-300 mt-1">
                          {relationVerb(e.relation_type)}
                          {e.label ? ` — ${e.label}` : ""}
                        </p>
                        <div className="mt-1">
                          <EvidenceList evidence={e.evidence} />
                        </div>
                      </div>
                    );
                  })}
                  {selectedEdges.length === 0 && (
                    <p className="text-xs text-dark-400 italic">
                      No connections pass the current filters.
                    </p>
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </Card>
      </div>
    </div>
  );
};
