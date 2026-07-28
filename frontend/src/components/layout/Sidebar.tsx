"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const sidebarSections = [
  {
    title: "Main",
    links: [
      { href: "/", label: "Home", icon: "🏠" },
      { href: "/upload", label: "Upload", icon: "📤" },
      { href: "/dashboard", label: "Dashboard", icon: "📊" },
    ],
  },
  {
    title: "Explore",
    links: [
      { href: "/timeline", label: "Timeline", icon: "📅" },
      { href: "/search", label: "Ask AI", icon: "🔍" },
    ],
  },
];

export const Sidebar: React.FC = () => {
  const pathname = usePathname();

  return (
    <aside className="hidden lg:flex flex-col fixed left-0 top-16 bottom-0 w-64 bg-dark-800/50 backdrop-blur-sm border-r border-dark-400/20 z-40 py-6 px-4 overflow-y-auto">
      {sidebarSections.map((section) => (
        <div key={section.title} className="mb-6">
          <p className="text-[10px] font-semibold text-dark-400 uppercase tracking-wider px-3 mb-2">
            {section.title}
          </p>
          <div className="space-y-0.5">
            {section.links.map((link) => {
              const isActive =
                link.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 group ${
                    isActive
                      ? "bg-primary-600/10 text-primary-400 border border-primary-500/15"
                      : "text-dark-200 hover:bg-dark-600/40 hover:text-white"
                  }`}
                >
                  <span
                    className={`text-base transition-transform ${
                      isActive ? "scale-110" : "group-hover:scale-110"
                    }`}
                  >
                    {link.icon}
                  </span>
                  {link.label}
                  {isActive && (
                    <span className="ml-auto w-1.5 h-1.5 rounded-full bg-primary-400" />
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      ))}

      {/* Bottom section */}
      <div className="mt-auto pt-4 border-t border-dark-400/20">
        <div className="px-3 py-3 rounded-xl bg-dark-700/40 border border-dark-400/20">
          <p className="text-[10px] text-dark-300 font-medium uppercase tracking-wider mb-1">
            Tech Stack
          </p>
          <div className="flex flex-wrap gap-1">
            {["FastAPI", "ChromaDB", "GPT-4o", "Next.js"].map((tech) => (
              <span
                key={tech}
                className="px-1.5 py-0.5 rounded bg-dark-600/60 text-dark-200 text-[9px]"
              >
                {tech}
              </span>
            ))}
          </div>
        </div>
      </div>
    </aside>
  );
};
