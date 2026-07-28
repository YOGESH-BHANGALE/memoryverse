"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { findSimilar } from "@/lib/api";
import type { Milestone, EntityCategory } from "@/lib/types";

interface TimelineViewProps {
  milestones: Milestone[];
}

const staggerContainer = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.08,
    },
  },
};

const milestoneVariant = {
  hidden: { opacity: 0, x: -30 },
  show: {
    opacity: 1,
    x: 0,
    transition: { duration: 0.4, ease: "easeOut" },
  },
};

const dotPulse = {
  initial: { scale: 0 },
  animate: {
    scale: 1,
    transition: { type: "spring", stiffness: 300, damping: 15 },
  },
};

const categoryIcons: Record<string, string> = {
  skill: "⚡",
  project: "🚀",
  certification: "📜",
  internship: "🏢",
  achievement: "🏆",
  academics: "🎓",
};

interface RelatedItem {
  title: string;
  category: string;
  score: number;
}

function MilestoneCard({ milestone }: { milestone: Milestone }) {
  const [expanded, setExpanded] = useState(false);
  const [related, setRelated] = useState<RelatedItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [fetched, setFetched] = useState(false);

  const handleClick = async () => {
    const willExpand = !expanded;
    setExpanded(willExpand);

    if (willExpand && !fetched && milestone.id) {
      setLoading(true);
      try {
        const res = await findSimilar(milestone.id, 5);
        const items: RelatedItem[] = (res.similar || [])
          .map((chunk: any) => ({
            title: chunk.metadata?.title || chunk.text?.split(":")[0] || "Unknown",
            category: chunk.metadata?.category || "unknown",
            score: Math.round((chunk.combined_score || chunk.semantic_score || 0) * 100),
          }))
          .filter((item: RelatedItem) => item.title.toLowerCase() !== milestone.title.toLowerCase())
          .slice(0, 3);
        setRelated(items);
      } catch (err) {
        console.error("Failed to fetch related:", err);
        setRelated([]);
      } finally {
        setLoading(false);
        setFetched(true);
      }
    }
  };

  return (
    <motion.div
      className="flex-1 cursor-pointer"
      whileHover={{ x: 4 }}
      transition={{ duration: 0.2 }}
      onClick={handleClick}
    >
      <Card hover>
        <div className="flex items-start justify-between mb-2">
          <div>
            <h3 className="text-sm font-semibold text-white">
              {milestone.title}
            </h3>
            {milestone.date && (
              <p className="text-xs text-dark-300 mt-0.5">
                📅 {milestone.date}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Badge category={milestone.category} />
            <span className="text-[10px] text-dark-400 font-mono">
              ★{milestone.importance_score}
            </span>
            <span className={`text-dark-400 text-xs transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}>
              ▼
            </span>
          </div>
        </div>

        {milestone.description && (
          <p className="text-xs text-dark-100 mt-1.5 leading-relaxed">
            {milestone.description}
          </p>
        )}

        {/* Tags */}
        {milestone.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2.5">
            {milestone.tags.map((tag) => (
              <span
                key={tag}
                className="px-1.5 py-0.5 rounded bg-dark-500/60 text-dark-100 text-[10px]"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Related entities count hint */}
        {!expanded && milestone.related_entities.length > 0 && (
          <p className="text-[10px] text-dark-400 mt-2">
            🔗 {milestone.related_entities.length} related — click to explore
          </p>
        )}

        {/* ── Expanded Related Section ── */}
        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="mt-3 pt-3 border-t border-dark-500/50">
                <div className="flex items-center gap-1.5 mb-2">
                  <span className="text-[10px] uppercase tracking-wider text-dark-300 font-semibold">
                    🔗 Related Entities
                  </span>
                </div>

                {loading && (
                  <div className="flex items-center gap-2 py-1">
                    <div className="w-3 h-3 border-2 border-primary-400 border-t-transparent rounded-full animate-spin" />
                    <span className="text-xs text-dark-400">Finding connections…</span>
                  </div>
                )}

                {!loading && related.length === 0 && fetched && (
                  <p className="text-xs text-dark-400 italic">No related entities found</p>
                )}

                {!loading && related.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {related.map((item, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-dark-500/80 border border-dark-400/30 text-xs"
                      >
                        <span className="text-[10px]">{categoryIcons[item.category] || "📎"}</span>
                        <span className="text-dark-100 font-medium">{item.title}</span>
                        <span className="text-dark-400 text-[10px]">{item.score}%</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>
    </motion.div>
  );
}

export const TimelineView: React.FC<TimelineViewProps> = ({ milestones }) => {
  if (milestones.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <Card className="text-center py-16">
          <p className="text-6xl mb-4">📭</p>
          <p className="text-lg font-semibold text-white">No milestones yet</p>
          <p className="text-sm text-dark-200 mt-1">
            Upload a document to start building your journey timeline
          </p>
        </Card>
      </motion.div>
    );
  }

  // Group milestones by year
  const grouped: Record<string, Milestone[]> = {};
  milestones.forEach((m) => {
    const year = m.date ? m.date.split("-")[0] : "Undated";
    if (!grouped[year]) grouped[year] = [];
    grouped[year].push(m);
  });
  const years = Object.keys(grouped).sort().reverse();

  return (
    <div className="relative">
      {/* Main vertical line */}
      <div className="absolute left-[23px] top-0 bottom-0 w-px bg-gradient-to-b from-primary-500 via-accent-500/40 to-transparent" />

      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate="show"
        className="space-y-8"
      >
        {years.map((year) => (
          <div key={year}>
            {/* Year label */}
            <motion.div
              variants={milestoneVariant}
              className="flex items-center gap-3 mb-4"
            >
              <div className="w-12 h-8 rounded-lg bg-primary-600/20 border border-primary-500/30 flex items-center justify-center z-10">
                <span className="text-xs font-bold text-primary-400">
                  {year}
                </span>
              </div>
              <div className="h-px flex-1 bg-dark-400/30" />
            </motion.div>

            {/* Milestones for this year */}
            <div className="space-y-4 ml-0">
              {grouped[year].map((milestone) => (
                <motion.div
                  key={milestone.id}
                  variants={milestoneVariant}
                  className="relative flex gap-4"
                >
                  {/* Animated dot */}
                  <motion.div
                    variants={dotPulse}
                    initial="initial"
                    animate="animate"
                    className="relative z-10 flex-shrink-0"
                  >
                    <div className="w-12 h-12 rounded-xl bg-dark-700 border border-dark-400/50 flex items-center justify-center">
                      <motion.div
                        className={`w-3 h-3 rounded-full ${
                          milestone.importance_score >= 8
                            ? "bg-primary-500"
                            : milestone.importance_score >= 5
                            ? "bg-accent-500"
                            : "bg-dark-300"
                        }`}
                        animate={
                          milestone.importance_score >= 8
                            ? {
                                boxShadow: [
                                  "0 0 0 0 rgba(92, 124, 250, 0.4)",
                                  "0 0 0 8px rgba(92, 124, 250, 0)",
                                ],
                              }
                            : {}
                        }
                        transition={
                          milestone.importance_score >= 8
                            ? { duration: 2, repeat: Infinity }
                            : {}
                        }
                      />
                    </div>
                  </motion.div>

                  {/* Content card with related section */}
                  <MilestoneCard milestone={milestone} />
                </motion.div>
              ))}
            </div>
          </div>
        ))}
      </motion.div>
    </div>
  );
};

