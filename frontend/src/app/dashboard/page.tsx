"use client";

import React, { useEffect } from "react";
import { motion } from "framer-motion";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { SkillGraph } from "@/components/ui/SkillGraph";
import { useAppStore } from "@/lib/store";
import type { EntityCategory } from "@/lib/types";

const statCards: { label: string; icon: string; category: EntityCategory }[] = [
  { label: "Skills", icon: "⚡", category: "skill" },
  { label: "Projects", icon: "🚀", category: "project" },
  { label: "Certifications", icon: "📜", category: "certification" },
  { label: "Internships", icon: "🏢", category: "internship" },
  { label: "Achievements", icon: "🏆", category: "achievement" },
];

export default function DashboardPage() {
  const { profile, profileLoading, profileError, fetchProfile } = useAppStore();

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  // Build skills data for the graph from profile
  const skillsData =
    profile?.top_skills.map((name, i) => ({
      name,
      level: Math.max(4, 10 - i), // descending from 10
      category: "General",
    })) || [];

  return (
    <div className="space-y-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-3xl font-bold text-white">Dashboard</h1>
        <p className="text-dark-200 mt-1">
          Overview of your extracted knowledge graph
        </p>
      </motion.div>

      {/* Profile card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
      >
        <Card glow className="bg-gradient-to-br from-dark-700 to-dark-800">
          {profileLoading ? (
            <div className="flex items-center gap-3">
              <div className="w-14 h-14 rounded-xl bg-dark-600 animate-pulse" />
              <div className="space-y-2">
                <div className="w-40 h-5 bg-dark-600 rounded animate-pulse" />
                <div className="w-56 h-3 bg-dark-600 rounded animate-pulse" />
              </div>
            </div>
          ) : profileError ? (
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-xl bg-dark-600/50 flex items-center justify-center text-2xl">
                📭
              </div>
              <div>
                <p className="text-sm text-dark-200">{profileError}</p>
                <a
                  href="/upload"
                  className="text-xs text-primary-400 hover:underline mt-1 inline-block"
                >
                  → Upload a document to get started
                </a>
              </div>
            </div>
          ) : profile ? (
            <div>
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center text-2xl shadow-lg shadow-primary-500/20">
                  🧠
                </div>
                <div>
                  <h2 className="text-xl font-bold text-white">
                    {profile.name || profile.user_id}
                  </h2>
                  <p className="text-sm text-dark-200">{profile.summary}</p>
                </div>
                <div className="ml-auto text-right">
                  <p className="text-3xl font-bold text-primary-400">
                    {profile.total_entities}
                  </p>
                  <p className="text-xs text-dark-300">Total Entities</p>
                </div>
              </div>

              {/* Top skills pills */}
              {profile.top_skills.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {profile.top_skills.map((skill, i) => (
                    <motion.span
                      key={skill}
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ delay: 0.1 + i * 0.03 }}
                      className="px-3 py-1 rounded-lg bg-primary-500/10 text-primary-400 text-xs font-medium border border-primary-500/20"
                    >
                      {skill}
                    </motion.span>
                  ))}
                </div>
              )}
            </div>
          ) : null}
        </Card>
      </motion.div>

      {/* Stat grid */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="grid grid-cols-2 md:grid-cols-5 gap-4"
      >
        {statCards.map((stat, i) => (
          <motion.div
            key={stat.category}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 + i * 0.04 }}
            whileHover={{ y: -2 }}
          >
            <Card hover className="text-center py-4">
              <span className="text-3xl">{stat.icon}</span>
              <p className="mt-2 text-sm font-medium text-dark-200">
                {stat.label}
              </p>
              <Badge category={stat.category} className="mt-2" />
            </Card>
          </motion.div>
        ))}
      </motion.div>

      {/* Skills Graph */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25 }}
      >
        <h2 className="text-lg font-semibold text-white mb-4">
          📊 Skills Overview
        </h2>
        <SkillGraph skills={skillsData} />
      </motion.div>

      {/* Quick actions */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <Card>
          <h3 className="text-lg font-semibold text-white mb-4">
            Quick Actions
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {[
              { href: "/upload", icon: "📤", label: "Upload Document" },
              { href: "/timeline", icon: "📅", label: "View Timeline" },
              { href: "/search", icon: "🔍", label: "Ask MemoryVerse" },
            ].map((action) => (
              <a
                key={action.href}
                href={action.href}
                className="group flex items-center gap-3 px-4 py-3 rounded-xl bg-dark-600 hover:bg-dark-500 transition-all hover:-translate-y-0.5"
              >
                <span className="text-xl group-hover:scale-110 transition-transform">
                  {action.icon}
                </span>
                <span className="text-sm text-white">{action.label}</span>
              </a>
            ))}
          </div>
        </Card>
      </motion.div>
    </div>
  );
}
