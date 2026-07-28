import React from "react";
import clsx from "clsx";
import type { EntityCategory } from "@/lib/types";

interface BadgeProps {
  category: EntityCategory;
  className?: string;
}

const categoryStyles: Record<EntityCategory, string> = {
  skill: "bg-blue-500/15 text-blue-400 ring-blue-500/30",
  project: "bg-emerald-500/15 text-emerald-400 ring-emerald-500/30",
  certification: "bg-amber-500/15 text-amber-400 ring-amber-500/30",
  internship: "bg-purple-500/15 text-purple-400 ring-purple-500/30",
  achievement: "bg-rose-500/15 text-rose-400 ring-rose-500/30",
  academics: "bg-indigo-500/15 text-indigo-400 ring-indigo-500/30",
};

const categoryLabels: Record<EntityCategory, string> = {
  skill: "Skill",
  project: "Project",
  certification: "Certification",
  internship: "Internship",
  achievement: "Achievement",
  academics: "Academics",
};

export const Badge: React.FC<BadgeProps> = ({ category, className }) => {
  return (
    <span
      className={clsx(
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ring-1",
        categoryStyles[category],
        className
      )}
    >
      {categoryLabels[category]}
    </span>
  );
};
