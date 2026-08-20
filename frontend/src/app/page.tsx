"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import AetherBackground from "@/components/ui/aether-flow-hero";

const fadeUp = {
  hidden: { opacity: 0, y: 30 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.1, duration: 0.5, ease: "easeOut" },
  }),
};

const features = [
  {
    icon: "📄",
    title: "Smart Parsing",
    desc: "PDF, DOCX, TXT — auto-extracted via PyPDF2 and python-docx",
  },
  {
    icon: "🤖",
    // Named for what actually runs. The card said "GPT-4o", which the backend
    // has never called — it is Groq-hosted gpt-oss with a smaller fallback.
    title: "LLM Extraction",
    desc: "Groq-hosted LLM, strict-JSON extraction with a fallback model",
  },
  {
    icon: "🧬",
    title: "Entity Relations",
    desc: "Explainable links: shared tags, tech match, temporal proximity",
  },
  {
    icon: "📅",
    title: "Smart Timeline",
    desc: "Chronological journey view with importance scoring",
  },
  {
    icon: "🔍",
    title: "Hybrid Search",
    desc: "Semantic + BM25 with MMR reranking and RAG answers",
  },
  {
    icon: "⚡",
    title: "SSE Streaming",
    desc: "Real-time AI answers streamed token-by-token",
  },
];

export default function HomePage() {
  return (
    <>
      {/* Animated particle-network background (fixed, full-viewport) */}
      <AetherBackground />

      <div className="relative z-10 min-h-[85vh] flex flex-col">
        {/* Hero Section */}
        <div className="flex flex-col items-center justify-center text-center py-12 sm:py-16 relative">
          {/* Logo */}
          <motion.div
            custom={0}
            variants={fadeUp}
            initial="hidden"
            animate="show"
            className="relative z-10 w-20 h-20 rounded-2xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center text-white text-3xl font-bold shadow-2xl shadow-primary-500/30 mb-8"
            whileHover={{ scale: 1.1, rotate: 5 }}
          >
            M
          </motion.div>

          {/* Headline */}
          <motion.h1
            custom={1}
            variants={fadeUp}
            initial="hidden"
            animate="show"
            className="relative z-10 text-4xl sm:text-5xl md:text-6xl font-extrabold leading-tight"
          >
            <span className="bg-gradient-to-r from-white via-primary-200 to-accent-200 bg-clip-text text-transparent">
              MemoryVerse AI
            </span>
          </motion.h1>

          <motion.p
            custom={2}
            variants={fadeUp}
            initial="hidden"
            animate="show"
            className="relative z-10 mt-4 text-base sm:text-lg text-dark-100 max-w-2xl leading-relaxed"
          >
            Upload your resume, certificates, and project docs — AI extracts,
            categorizes, and connects your professional journey into an interactive
            knowledge graph with conversational search.
          </motion.p>

          {/* CTA Buttons */}
          <motion.div
            custom={3}
            variants={fadeUp}
            initial="hidden"
            animate="show"
            className="relative z-10 flex flex-col sm:flex-row justify-center gap-3 sm:gap-4 mt-8 w-full max-w-xs sm:w-auto sm:max-w-none"
          >
            <Link
              href="/upload"
              className="group inline-flex items-center justify-center gap-2 w-full sm:w-auto px-8 py-3.5 rounded-xl bg-gradient-to-r from-primary-600 to-primary-500 text-white font-semibold shadow-lg shadow-primary-500/25 hover:from-primary-700 hover:to-primary-600 transition-all duration-200 hover:shadow-xl hover:shadow-primary-500/30 hover:-translate-y-0.5"
            >
              <span className="group-hover:rotate-12 transition-transform">📤</span>
              Upload Document
            </Link>
            <Link
              href="/dashboard"
              className="group inline-flex items-center justify-center gap-2 w-full sm:w-auto px-8 py-3.5 rounded-xl bg-dark-600/80 backdrop-blur-sm text-dark-50 font-semibold border border-dark-400 hover:bg-dark-500 transition-all duration-200 hover:-translate-y-0.5"
            >
              <span className="group-hover:scale-110 transition-transform">📊</span>
              Dashboard
            </Link>
          </motion.div>

          {/* Tech badges */}
          <motion.div
            custom={4}
            variants={fadeUp}
            initial="hidden"
            animate="show"
            className="relative z-10 flex flex-wrap justify-center gap-2 mt-10"
          >
            {["FastAPI", "ChromaDB", "LangChain", "Groq", "Next.js", "Zustand"].map(
              (tech) => (
                <span
                  key={tech}
                  className="px-3 py-1 rounded-full bg-dark-700/60 backdrop-blur-sm border border-dark-400/40 text-xs text-dark-100 font-medium"
                >
                  {tech}
                </span>
              )
            )}
          </motion.div>
        </div>

        {/* Features Grid */}
        <motion.div
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-4"
        >
          {features.map((f, i) => (
            <motion.div
              key={f.title}
              custom={i + 5}
              variants={fadeUp}
              initial="hidden"
              animate="show"
              whileHover={{ y: -4, transition: { duration: 0.2 } }}
              className="rounded-2xl border border-dark-400/30 bg-dark-700/50 backdrop-blur-sm p-5 hover:border-primary-500/20 transition-colors"
            >
              <span className="text-3xl">{f.icon}</span>
              <h3 className="text-sm font-semibold text-white mt-3">{f.title}</h3>
              <p className="text-xs text-dark-200 mt-1 leading-relaxed">
                {f.desc}
              </p>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </>
  );
}
