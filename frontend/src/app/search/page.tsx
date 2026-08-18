"use client";

import React, { useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { SearchBar } from "@/components/search/SearchBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useAppStore } from "@/lib/store";
import { fileUrl } from "@/lib/api";
import type { SourceAttribution, SourceDocument } from "@/lib/types";

/**
 * Turns the router's machine intent into something a reviewer can read.
 * The raw value is compact on purpose ("categories=internship; documents") —
 * good for logs, but it should not be the label a user sees.
 */
function describeIntent(intent: string): string {
  const parts = intent
    .split(";")
    .map((p) => p.trim())
    .filter(Boolean);
  const words: string[] = [];

  for (const part of parts) {
    if (part.startsWith("categories=")) {
      words.push(
        part
          .slice("categories=".length)
          .split(",")
          .map((c) => c.trim().replace(/_/g, " "))
          .filter(Boolean)
          .join(" + ")
      );
    } else if (part.startsWith("documents:")) {
      words.push(`${part.slice("documents:".length).trim()} files`);
    } else if (part === "documents") {
      words.push("original files");
    } else if (part === "latest") {
      words.push("most recent");
    } else if (part !== "none") {
      words.push(part);
    }
  }
  return words.join(" · ");
}

export default function SearchPage() {
  const {
    searchResult,
    streamingAnswer,
    streamingSources,
    searchIntent,
    searchDocuments,
    isStreaming,
    searchLoading,
    searchError,
    chatHistory,
    doSearchStream,
    clearSearch,
  } = useAppStore();

  const chatEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory, streamingAnswer]);

  const handleSearch = (query: string) => {
    doSearchStream(query);
  };

  // Current sources
  const displaySources =
    streamingSources.length > 0
      ? streamingSources
      : searchResult?.sources || [];

  const documents: SourceDocument[] =
    searchDocuments.length > 0 ? searchDocuments : searchResult?.documents || [];

  const intentLabel = describeIntent(searchIntent || searchResult?.intent || "");

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between mb-6 flex-shrink-0"
      >
        <div>
          <h1 className="text-3xl font-bold text-white">Ask MemoryVerse</h1>
          <p className="text-dark-200 mt-1">
            Conversational AI search over your knowledge base
          </p>
        </div>
        {chatHistory.length > 0 && (
          <Button variant="ghost" size="sm" onClick={clearSearch}>
            Clear Chat
          </Button>
        )}
      </motion.div>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-1">
        {/* Empty state */}
        {chatHistory.length === 0 && !isStreaming && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-center justify-center h-full"
          >
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary-500/20 to-accent-500/20 flex items-center justify-center text-3xl mb-4">
              🧠
            </div>
            <p className="text-lg font-semibold text-white">
              What would you like to know?
            </p>
            <p className="text-sm text-dark-200 mt-1 text-center max-w-md">
              Ask questions about your skills, projects, certifications, or any
              topic from your uploaded documents.
            </p>

            {/* The four patterns the retrieval router handles explicitly:
                two category questions, one document-type question, one
                document-type + recency question. */}
            <div className="flex flex-wrap justify-center gap-2 mt-6">
              {[
                "show all my certificates",
                "show my AI projects",
                "show internship documents",
                "show my latest resume",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => handleSearch(suggestion)}
                  className="px-4 py-2 rounded-xl bg-dark-700 border border-dark-400/40 text-xs text-dark-100 hover:bg-dark-600 hover:text-white hover:border-dark-300 transition-all"
                >
                  {suggestion}
                </button>
              ))}
            </div>

            <div className="flex justify-center gap-2 mt-6">
              <span className="px-3 py-1 rounded-full bg-blue-500/10 text-blue-400 text-[10px] ring-1 ring-blue-500/20">
                🧠 Semantic + BM25
              </span>
              <span className="px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 text-[10px] ring-1 ring-emerald-500/20">
                ⚡ SSE Streaming
              </span>
              <span className="px-3 py-1 rounded-full bg-amber-500/10 text-amber-400 text-[10px] ring-1 ring-amber-500/20">
                📎 Source Citations
              </span>
            </div>
          </motion.div>
        )}

        {/* Chat messages */}
        <AnimatePresence>
          {chatHistory.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className={`flex ${
                msg.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div
                className={`max-w-[80%] ${
                  msg.role === "user"
                    ? "bg-primary-600/20 border border-primary-500/20 rounded-2xl rounded-tr-sm"
                    : "bg-dark-700 border border-dark-400/30 rounded-2xl rounded-tl-sm"
                } px-4 py-3`}
              >
                {msg.role === "ai" && (
                  <p className="text-[10px] text-primary-400 font-semibold mb-1">
                    🤖 MemoryVerse
                  </p>
                )}
                <p className="text-sm text-dark-50 leading-relaxed whitespace-pre-wrap">
                  {msg.content}
                </p>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Streaming answer (not yet in chatHistory) */}
        {isStreaming && streamingAnswer && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex justify-start"
          >
            <div className="max-w-[80%] bg-dark-700 border border-dark-400/30 rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex items-center gap-2 mb-1">
                <p className="text-[10px] text-primary-400 font-semibold">
                  🤖 MemoryVerse
                </p>
                <span className="flex items-center gap-1 text-[10px] text-emerald-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Streaming
                </span>
              </div>
              <p className="text-sm text-dark-50 leading-relaxed whitespace-pre-wrap">
                {streamingAnswer}
                <span className="inline-block w-2 h-4 bg-primary-400 ml-0.5 animate-pulse" />
              </p>
            </div>
          </motion.div>
        )}

        {/* Loading indicator (before streaming starts) */}
        {searchLoading && !streamingAnswer && !isStreaming && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex justify-start"
          >
            <div className="bg-dark-700 border border-dark-400/30 rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-primary-400 rounded-full animate-bounce" />
                <div
                  className="w-2 h-2 bg-primary-400 rounded-full animate-bounce"
                  style={{ animationDelay: "0.15s" }}
                />
                <div
                  className="w-2 h-2 bg-primary-400 rounded-full animate-bounce"
                  style={{ animationDelay: "0.3s" }}
                />
              </div>
            </div>
          </motion.div>
        )}

        {/* Error */}
        {searchError && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex justify-start"
          >
            <Card className="border-red-500/30 bg-red-500/5 max-w-[80%]">
              <p className="text-red-400 text-sm">❌ {searchError}</p>
            </Card>
          </motion.div>
        )}

        {/* How the router read the question. Shown so a wrong reading is
            visible instead of silently returning the wrong documents. */}
        {intentLabel && (chatHistory.length > 0 || isStreaming) && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center gap-2 flex-wrap"
          >
            <span className="text-[10px] text-dark-400 uppercase tracking-wider">
              Understood as
            </span>
            <span className="px-2 py-0.5 rounded-full bg-primary-500/10 text-primary-300 text-[10px] ring-1 ring-primary-500/25 font-medium">
              🎯 {intentLabel}
            </span>
          </motion.div>
        )}

        {/* Original documents — the answer to "show my latest resume" is a file,
            not a paragraph, so link straight to the untouched original. */}
        {documents.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <Card className="bg-dark-800/50 max-w-[80%] border-emerald-500/20">
              <h4 className="text-[10px] font-semibold text-dark-300 mb-2 uppercase tracking-wider">
                🗂️ Original documents ({documents.length})
              </h4>
              <div className="space-y-1.5">
                {documents.map((doc: SourceDocument) => {
                  const href = doc.download_url
                    ? fileUrl(doc.download_url)
                    : doc.source_file?.startsWith("http")
                    ? doc.source_file
                    : "";

                  return (
                    <div
                      key={doc.file_id || doc.source_file}
                      className="flex items-center justify-between gap-2 px-2 py-1.5 rounded bg-dark-700/40 hover:bg-dark-700/70 transition-colors"
                    >
                      <div className="min-w-0">
                        {href ? (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1.5 text-[11px] text-emerald-400 hover:text-emerald-300 underline font-medium truncate"
                            title={`Open the original ${doc.file_type || "file"}`}
                          >
                            <span>📄</span>
                            <span className="truncate">{doc.source_file}</span>
                          </a>
                        ) : (
                          <span className="text-[11px] text-dark-200 truncate font-mono">
                            {doc.source_file}
                          </span>
                        )}
                        <p className="text-[10px] text-dark-400 mt-0.5">
                          {doc.file_type || "file"} · {doc.chunk_count} chunk
                          {doc.chunk_count === 1 ? "" : "s"}
                          {doc.entity_count > 0
                            ? ` · ${doc.entity_count} extracted`
                            : ""}
                          {doc.uploaded_at
                            ? ` · ${doc.uploaded_at.slice(0, 10)}`
                            : ""}
                        </p>
                      </div>
                      {href && (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex-shrink-0 px-2 py-1 rounded bg-emerald-500/10 text-emerald-400 text-[10px] ring-1 ring-emerald-500/25 hover:bg-emerald-500/20 transition-colors"
                        >
                          Download
                        </a>
                      )}
                    </div>
                  );
                })}
              </div>
              <p className="text-[10px] text-dark-400 mt-2">
                Served in the original format, untouched, from
                <span className="font-mono"> /api/files/…</span>
              </p>
            </Card>
          </motion.div>
        )}

        {/* Sources (shown after streaming completes) */}
        {displaySources.length > 0 && !isStreaming && chatHistory.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="ml-0"
          >
            <Card className="bg-dark-800/50 max-w-[80%]">
              <h4 className="text-[10px] font-semibold text-dark-300 mb-2 uppercase tracking-wider">
                📎 Sources
              </h4>
              <div className="space-y-1">
                {displaySources
                  .slice(0, 5)
                  .map((src: SourceAttribution, i: number) => {
                    // Named `href` rather than `fileUrl` so it does not shadow
                    // the imported helper of that name.
                    const href = src.file_id
                      ? fileUrl(src.file_id)
                      : src.source_file?.startsWith("http")
                      ? src.source_file
                      : null;

                    return (
                      <div
                        key={src.chunk_id || i}
                        className="flex items-center justify-between px-2 py-1.5 rounded bg-dark-700/40 hover:bg-dark-700/70 transition-colors"
                      >
                        {href ? (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1.5 text-[11px] text-primary-400 hover:text-primary-300 underline font-medium truncate"
                            title={`Open / Download ${src.source_file}`}
                          >
                            <span>📄</span>
                            <span className="truncate">
                              {src.source_file || src.collection}
                            </span>
                          </a>
                        ) : (
                          <span className="text-[11px] text-dark-200 truncate font-mono">
                            {src.source_file || src.collection}
                          </span>
                        )}
                        <span className="text-[10px] text-primary-400 font-mono ml-2 flex-shrink-0">
                          {(src.score * 100).toFixed(0)}%
                        </span>
                      </div>
                    );
                  })}
              </div>
            </Card>
          </motion.div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Search input — fixed at bottom */}
      <div className="flex-shrink-0 pt-2 border-t border-dark-400/20">
        <SearchBar
          onSearch={handleSearch}
          loading={searchLoading}
          chatMode
          placeholder="Ask about your skills, projects, or journey…"
        />
      </div>
    </div>
  );
}
