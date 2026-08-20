"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAppStore } from "@/lib/store";
import { getOrCreateUserId } from "@/lib/user";
import { BrainMark } from "@/components/ui/BrainMark";

const navLinks = [
  { href: "/upload", label: "Upload", icon: "📤" },
  { href: "/dashboard", label: "Dashboard", icon: "📊" },
  { href: "/timeline", label: "Timeline", icon: "📅" },
  { href: "/graph", label: "Map", icon: "🕸️" },
  { href: "/search", label: "Search", icon: "🔍" },
];

export const Navbar: React.FC = () => {
  const pathname = usePathname();
  const { userId, setUserId } = useAppStore();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const id = getOrCreateUserId();
    if (id && id !== userId) {
      setUserId(id);
    }
  }, [setUserId, userId]);

  const displayId = mounted && userId ? `${userId.substring(0, 8)}…` : "";

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 h-16 bg-dark-800/80 backdrop-blur-xl border-b border-dark-400/30">
      <div className="max-w-screen-xl mx-auto h-full flex items-center justify-between px-6">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2.5 group">
          <BrainMark
            className="w-8 h-8 shrink-0 transition-transform group-hover:scale-110"
            glow="sm"
            gradientId="brainGradientNav"
            strokeWidth={1.8}
            nodes={false}
          />
          <span className="text-lg font-bold bg-gradient-to-r from-white to-dark-100 bg-clip-text text-transparent hidden sm:block">
            MemoryVerse
          </span>
        </Link>

        {/* Desktop nav links + Session Badge */}
        <div className="hidden md:flex items-center gap-3">
          <div className="flex items-center gap-1">
            {navLinks.map((link) => {
              const isActive = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? "bg-primary-600/15 text-primary-400"
                      : "text-dark-200 hover:text-white hover:bg-dark-600/50"
                  }`}
                >
                  <span className="text-base">{link.icon}</span>
                  {link.label}
                </Link>
              );
            })}
          </div>

          {/* User Session Badge */}
          {displayId && (
            <div
              className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-dark-700/80 border border-dark-400/40 text-[11px] font-mono text-dark-200"
              title={`Active Session User ID: ${userId}`}
            >
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span>{displayId}</span>
            </div>
          )}
        </div>

        {/* Mobile hamburger — simple version */}
        <div className="md:hidden flex items-center gap-2">
          {navLinks.map((link) => {
            const isActive = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`p-2 rounded-lg ${
                  isActive
                    ? "bg-primary-600/15 text-primary-400"
                    : "text-dark-200"
                }`}
              >
                <span className="text-lg">{link.icon}</span>
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
};
