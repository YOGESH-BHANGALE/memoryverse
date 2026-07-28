"use client";

import React, { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/Button";

interface SearchBarProps {
  onSearch: (query: string) => void;
  loading?: boolean;
  placeholder?: string;
  chatMode?: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({
  onSearch,
  loading = false,
  placeholder = "Ask anything about your journey…",
  chatMode = false,
}) => {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLTextAreaElement | HTMLInputElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      onSearch(query.trim());
      if (chatMode) setQuery("");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey && chatMode) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  // Auto-resize textarea in chat mode
  useEffect(() => {
    if (chatMode && inputRef.current && "style" in inputRef.current) {
      const el = inputRef.current as HTMLTextAreaElement;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 120) + "px";
    }
  }, [query, chatMode]);

  return (
    <motion.form
      onSubmit={handleSubmit}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative"
    >
      <div className="flex gap-3 items-end">
        <div className="relative flex-1">
          {/* Search icon */}
          <div className="absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none">
            {loading ? (
              <div className="w-5 h-5 border-2 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" />
            ) : (
              <svg
                className="w-5 h-5 text-dark-300"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
            )}
          </div>

          {chatMode ? (
            <textarea
              ref={inputRef as React.RefObject<HTMLTextAreaElement>}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              rows={1}
              className="w-full pl-12 pr-4 py-3.5 rounded-xl bg-dark-700 border border-dark-400/50 text-white placeholder-dark-300 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all resize-none"
              style={{ minHeight: "48px" }}
            />
          ) : (
            <input
              ref={inputRef as React.RefObject<HTMLInputElement>}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={placeholder}
              className="w-full pl-12 pr-4 py-3.5 rounded-xl bg-dark-700 border border-dark-400/50 text-white placeholder-dark-300 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
            />
          )}
        </div>

        <Button
          type="submit"
          loading={loading}
          size="lg"
          disabled={!query.trim()}
          className="flex-shrink-0"
        >
          {chatMode ? (
            <svg
              className="w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
              />
            </svg>
          ) : (
            "Search"
          )}
        </Button>
      </div>

      {chatMode && (
        <p className="text-[10px] text-dark-400 mt-1.5 ml-1">
          Press Enter to send • Shift+Enter for new line
        </p>
      )}
    </motion.form>
  );
};
