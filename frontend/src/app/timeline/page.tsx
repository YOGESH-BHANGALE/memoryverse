"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { TimelineView } from "@/components/timeline/TimelineView";
import { Button } from "@/components/ui/Button";
import { useAppStore } from "@/lib/store";
import type { EntityCategory } from "@/lib/types";

const categories: (EntityCategory | "all")[] = [
  "all",
  "skill",
  "project",
  "certification",
  "internship",
  "achievement",
];

const categoryLabels: Record<string, string> = {
  all: "All",
  skill: "Skills",
  project: "Projects",
  certification: "Certifications",
  internship: "Internships",
  achievement: "Achievements",
};

export default function TimelinePage() {
  const { timeline, timelineLoading, timelineError, fetchTimeline } =
    useAppStore();
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [yearFilter, setYearFilter] = useState("");

  useEffect(() => {
    fetchTimeline();
  }, [fetchTimeline]);

  const handleFilter = (cat: string) => {
    setSelectedCategory(cat);
    fetchTimeline(
      yearFilter || undefined,
      cat === "all" ? undefined : cat
    );
  };

  const handleYearApply = () => {
    fetchTimeline(
      yearFilter || undefined,
      selectedCategory === "all" ? undefined : selectedCategory
    );
  };

  const milestoneCount = timeline?.milestones.length || 0;

  return (
    <div className="space-y-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-start justify-between"
      >
        <div>
          <h1 className="text-3xl font-bold text-white">Journey Timeline</h1>
          <p className="text-dark-200 mt-1">
            Your professional journey, mapped chronologically
            {milestoneCount > 0 && (
              <span className="text-primary-400 ml-1">
                ({milestoneCount} milestone{milestoneCount !== 1 ? "s" : ""})
              </span>
            )}
          </p>
        </div>
      </motion.div>

      {/* Filters */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="flex flex-wrap gap-3 items-center"
      >
        {/* Category pills */}
        <div className="flex gap-1 flex-wrap">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => handleFilter(cat)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                selectedCategory === cat
                  ? "bg-primary-600/20 text-primary-400 border border-primary-500/30 shadow-sm shadow-primary-500/10"
                  : "bg-dark-700 text-dark-200 hover:bg-dark-600 hover:text-white"
              }`}
            >
              {categoryLabels[cat]}
            </button>
          ))}
        </div>

        {/* Year filter */}
        <div className="flex items-center gap-2 ml-auto">
          <input
            type="text"
            value={yearFilter}
            onChange={(e) => setYearFilter(e.target.value)}
            placeholder="Year"
            className="px-3 py-2 rounded-lg bg-dark-700 border border-dark-400/50 text-sm text-white placeholder-dark-300 w-24 focus:outline-none focus:ring-2 focus:ring-primary-500/50"
          />
          <Button onClick={handleYearApply} variant="secondary" size="sm">
            Filter
          </Button>
        </div>
      </motion.div>

      {/* Loading */}
      {timelineLoading && (
        <div className="flex items-center justify-center py-20">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
            className="w-8 h-8 border-2 border-primary-500/30 border-t-primary-500 rounded-full"
          />
        </div>
      )}

      {/* Error */}
      {timelineError && !timelineLoading && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center py-12"
        >
          <p className="text-dark-200">{timelineError}</p>
        </motion.div>
      )}

      {/* Timeline */}
      {!timelineLoading && timeline && (
        <TimelineView milestones={timeline.milestones} />
      )}
    </div>
  );
}
