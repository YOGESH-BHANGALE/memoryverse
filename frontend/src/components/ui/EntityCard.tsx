"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { findSimilar } from "@/lib/api";
import type { CategorisedEntity, EntityCategory, RetrievedChunk } from "@/lib/types";

interface EntityCardProps {
  entity: CategorisedEntity;
  index?: number;
  onClick?: (entity: CategorisedEntity) => void;
}

const categoryIcons: Record<EntityCategory, string> = {
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

export const EntityCard: React.FC<EntityCardProps> = ({
  entity,
  index = 0,
  onClick,
}) => {
  const data = entity.data || {};
  const [expanded, setExpanded] = useState(false);
  const [related, setRelated] = useState<RelatedItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [fetched, setFetched] = useState(false);

  const handleToggle = async () => {
    // If the caller has an onClick, fire it
    onClick?.(entity);

    // Toggle the related section
    const willExpand = !expanded;
    setExpanded(willExpand);

    // Fetch related entities on first expand
    if (willExpand && !fetched && entity.id) {
      setLoading(true);
      try {
        const res = await findSimilar(entity.id, 5);
        const items: RelatedItem[] = (res.similar || [])
          .slice(0, 3)
          .map((chunk: any) => ({
            title: chunk.metadata?.title || chunk.text?.split(":")[0] || "Unknown",
            category: chunk.metadata?.category || "unknown",
            score: Math.round((chunk.combined_score || chunk.semantic_score || 0) * 100),
          }))
          // Filter out self
          .filter((item: RelatedItem) => item.title.toLowerCase() !== entity.title.toLowerCase());
        setRelated(items.slice(0, 3));
      } catch (err) {
        console.error("Failed to fetch related entities:", err);
        setRelated([]);
      } finally {
        setLoading(false);
        setFetched(true);
      }
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
      whileHover={{ y: -2, transition: { duration: 0.2 } }}
    >
      <Card
        hover
        className="cursor-pointer group"
        onClick={handleToggle}
      >
        <div className="flex items-start gap-3">
          {/* Icon */}
          <div className="w-10 h-10 rounded-xl bg-dark-600 flex items-center justify-center text-lg flex-shrink-0 group-hover:scale-110 transition-transform">
            {categoryIcons[entity.category]}
          </div>

          <div className="flex-1 min-w-0">
            {/* Title + Badge */}
            <div className="flex items-center gap-2 mb-1">
              <h4 className="text-sm font-semibold text-white truncate">
                {entity.title}
              </h4>
              <Badge category={entity.category} />
              {/* Expand indicator */}
              <span className={`text-dark-400 text-xs ml-auto transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}>
                ▼
              </span>
            </div>

            {/* Description / Details */}
            {data.description && (
              <p className="text-xs text-dark-200 line-clamp-2 leading-relaxed">
                {data.description}
              </p>
            )}

            {/* Meta row */}
            <div className="flex items-center gap-3 mt-2 flex-wrap">
              {entity.date && (
                <span className="text-xs text-dark-300">📅 {entity.date}</span>
              )}
              {data.company && (
                <span className="text-xs text-dark-300">🏢 {data.company}</span>
              )}
              {data.issuer && (
                <span className="text-xs text-dark-300">🏛️ {data.issuer}</span>
              )}
              {data.level && (
                <span className="text-xs text-dark-300 capitalize">
                  📊 {data.level}
                </span>
              )}
              <span className="text-xs text-dark-400 font-mono">
                ★ {entity.importance_score}/10
              </span>
            </div>

            {/* Tech stack tags */}
            {entity.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {entity.tags.slice(0, 5).map((tag) => (
                  <span
                    key={tag}
                    className="px-1.5 py-0.5 rounded bg-dark-500/60 text-dark-100 text-[10px]"
                  >
                    {tag}
                  </span>
                ))}
                {entity.tags.length > 5 && (
                  <span className="text-[10px] text-dark-400">
                    +{entity.tags.length - 5}
                  </span>
                )}
              </div>
            )}

            {/* ── Related Entities Section ── */}
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
                        🔗 Related
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
                            <span className="text-[10px]">{categoryIcons[item.category as EntityCategory] || "📎"}</span>
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
          </div>
        </div>
      </Card>
    </motion.div>
  );
};
