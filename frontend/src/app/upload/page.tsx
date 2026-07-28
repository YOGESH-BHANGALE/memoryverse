"use client";

import React from "react";

import { FileUploader } from "@/components/upload/FileUploader";
import { motion } from "framer-motion";

export default function UploadPage() {
  return (
    <div className="space-y-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-3xl font-bold text-white">Upload Document</h1>
        <p className="text-dark-200 mt-1">
          Upload your resume, certificates, or project docs for AI-powered extraction
        </p>
      </motion.div>

      <FileUploader />

      {/* Supported formats + pipeline */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="grid grid-cols-3 gap-4"
      >
        {[
          { icon: "📕", label: "PDF", desc: "Resumes, certificates, reports" },
          { icon: "📘", label: "DOCX", desc: "Word documents, cover letters" },
          { icon: "📗", label: "TXT", desc: "Plain text, readmes, notes" },
        ].map((fmt) => (
          <div
            key={fmt.label}
            className="flex items-center gap-3 px-4 py-3 rounded-xl bg-dark-700/50 border border-dark-400/30"
          >
            <span className="text-2xl">{fmt.icon}</span>
            <div>
              <p className="text-sm font-semibold text-white">{fmt.label}</p>
              <p className="text-xs text-dark-300">{fmt.desc}</p>
            </div>
          </div>
        ))}
      </motion.div>

      {/* Pipeline visualization */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="rounded-2xl border border-dark-400/30 bg-dark-700/30 p-6"
      >
        <h3 className="text-sm font-semibold text-dark-200 mb-4">
          🔄 Processing Pipeline
        </h3>
        <div className="flex items-center justify-between gap-2 overflow-x-auto">
          {[
            { step: "1", label: "Parse", icon: "📄" },
            { step: "2", label: "Extract", icon: "🤖" },
            { step: "3", label: "Categorize", icon: "🏷️" },
            { step: "4", label: "Embed", icon: "🧬" },
            { step: "5", label: "Relate", icon: "🔗" },
            { step: "6", label: "Store", icon: "💾" },
          ].map((s, i) => (
            <React.Fragment key={s.step}>
              <div className="flex flex-col items-center gap-1.5 min-w-[60px]">
                <div className="w-10 h-10 rounded-xl bg-dark-600 flex items-center justify-center text-lg">
                  {s.icon}
                </div>
                <span className="text-[10px] text-dark-300 font-medium">
                  {s.label}
                </span>
              </div>
              {i < 5 && (
                <div className="text-dark-500 text-sm flex-shrink-0">→</div>
              )}
            </React.Fragment>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
