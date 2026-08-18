"use client";

import React from "react";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
} from "recharts";
import { Card } from "@/components/ui/Card";

interface SkillData {
  name: string;
  level: number; // 1-10
  category: string;
}

interface SkillGraphProps {
  skills: SkillData[];
  /**
   * True number of extracted skills. `skills` is only the top slice the profile
   * returns, so without this the panel reported "Total Skills 15" directly under
   * a stat card reading 71 — two different numbers for the same thing.
   */
  total?: number;
}

// Pastel colors for categories
const COLORS = [
  "#5c7cfa", // primary blue
  "#f06595", // accent pink
  "#51cf66", // green
  "#fcc419", // yellow
  "#ff922b", // orange
  "#cc5de8", // purple
  "#22b8cf", // teal
  "#ff6b6b", // red
];

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-dark-700 border border-dark-400/50 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-sm font-semibold text-white">{d.fullName || d.name}</p>
      <p className="text-xs text-dark-200">Rank score {d.level}/10</p>
    </div>
  );
};

export const SkillGraph: React.FC<SkillGraphProps> = ({ skills, total }) => {
  if (!skills.length) {
    return (
      <Card className="text-center py-12">
        <p className="text-4xl mb-3">📊</p>
        <p className="text-sm text-dark-200">
          No skills data yet — upload a document to populate
        </p>
      </Card>
    );
  }

  // Prepare data for radar (top 8 skills)
  const radarData = skills
    .sort((a, b) => b.level - a.level)
    .slice(0, 8)
    .map((s) => ({
      name: s.name.length > 12 ? s.name.slice(0, 12) + "…" : s.name,
      fullName: s.name,
      level: s.level,
      category: s.category,
    }));

  // Prepare data for bar chart (all skills, sorted)
  const barData = skills
    .sort((a, b) => b.level - a.level)
    .slice(0, 15)
    .map((s) => ({
      name: s.name.length > 15 ? s.name.slice(0, 15) + "…" : s.name,
      fullName: s.name,
      level: s.level,
      category: s.category,
    }));

  // Group by category for stats
  const categoryGroups: Record<string, number> = {};
  skills.forEach((s) => {
    const cat = s.category || "General";
    categoryGroups[cat] = (categoryGroups[cat] || 0) + 1;
  });
  // Only worth showing when the caller supplied real categories; a single
  // "General 15" chip is a row of pixels that tells the reader nothing.
  const hasRealCategories = Object.keys(categoryGroups).length > 1;

  return (
    <div className="space-y-6">
      {/* Stats row */}
      <div className="grid grid-cols-2 gap-3">
        <Card className="text-center py-3">
          <p className="text-2xl font-bold text-primary-400">
            {total ?? skills.length}
          </p>
          <p className="text-xs text-dark-300">Skills extracted</p>
        </Card>
        <Card className="text-center py-3">
          <p className="text-2xl font-bold text-emerald-400">
            {Math.min(skills.length, 15)}
          </p>
          <p className="text-xs text-dark-300">Top skills charted</p>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Radar Chart */}
        <Card>
          <h3 className="text-sm font-semibold text-dark-200 mb-4">
            🎯 Top Skills Radar
          </h3>
          <ResponsiveContainer width="100%" height={280}>
            <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
              <PolarGrid
                stroke="#373a40"
                strokeDasharray="3 3"
              />
              <PolarAngleAxis
                dataKey="name"
                tick={{ fill: "#a6a7ab", fontSize: 11 }}
              />
              <PolarRadiusAxis
                angle={30}
                domain={[0, 10]}
                tick={{ fill: "#5c5f66", fontSize: 10 }}
              />
              <Radar
                name="Skill Level"
                dataKey="level"
                stroke="#5c7cfa"
                fill="#5c7cfa"
                fillOpacity={0.25}
                strokeWidth={2}
              />
            </RadarChart>
          </ResponsiveContainer>
        </Card>

        {/* Bar Chart */}
        <Card>
          <h3 className="text-sm font-semibold text-dark-200 mb-4">
            📊 Skill Levels
          </h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart
              data={barData}
              layout="vertical"
              margin={{ top: 0, right: 20, bottom: 0, left: 5 }}
            >
              <XAxis
                type="number"
                domain={[0, 10]}
                tick={{ fill: "#5c5f66", fontSize: 10 }}
                axisLine={{ stroke: "#373a40" }}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={100}
                tick={{ fill: "#a6a7ab", fontSize: 11 }}
                axisLine={{ stroke: "#373a40" }}
              />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="level" radius={[0, 4, 4, 0]} barSize={16}>
                {barData.map((_, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={COLORS[index % COLORS.length]}
                    fillOpacity={0.85}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Category breakdown */}
      {hasRealCategories && (
        <Card>
          <h3 className="text-sm font-semibold text-dark-200 mb-3">
            🏷️ By Category
          </h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(categoryGroups)
              .sort(([, a], [, b]) => b - a)
              .map(([cat, count], i) => (
                <span
                  key={cat}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
                  style={{
                    backgroundColor: `${COLORS[i % COLORS.length]}15`,
                    color: COLORS[i % COLORS.length],
                    border: `1px solid ${COLORS[i % COLORS.length]}30`,
                  }}
                >
                  {cat}
                  <span className="font-bold">{count}</span>
                </span>
              ))}
          </div>
        </Card>
      )}
    </div>
  );
};
