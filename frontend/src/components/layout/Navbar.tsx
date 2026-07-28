"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const navLinks = [
  { href: "/upload", label: "Upload", icon: "📤" },
  { href: "/dashboard", label: "Dashboard", icon: "📊" },
  { href: "/timeline", label: "Timeline", icon: "📅" },
  { href: "/search", label: "Search", icon: "🔍" },
];

export const Navbar: React.FC = () => {
  const pathname = usePathname();

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 h-16 bg-dark-800/80 backdrop-blur-xl border-b border-dark-400/30">
      <div className="max-w-screen-xl mx-auto h-full flex items-center justify-between px-6">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-3 group">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center text-white text-sm font-bold shadow-lg shadow-primary-500/20 group-hover:shadow-primary-500/40 transition-shadow">
            M
          </div>
          <span className="text-lg font-bold bg-gradient-to-r from-white to-dark-100 bg-clip-text text-transparent hidden sm:block">
            MemoryVerse
          </span>
        </Link>

        {/* Desktop nav links */}
        <div className="hidden md:flex items-center gap-1">
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
