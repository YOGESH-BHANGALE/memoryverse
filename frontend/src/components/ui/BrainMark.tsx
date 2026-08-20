import React from "react";
import { Brain } from "lucide-react";

/**
 * The MemoryVerse brand mark: a glowing, gradient line-art brain.
 *
 * Built on lucide's full two-hemisphere `Brain` icon, but re-skinned to match
 * the product identity — the stroke is painted with the brand blue→purple→pink
 * gradient instead of a flat colour, a soft two-tone neon glow is applied via
 * `drop-shadow`, and a few bright nodes sit on the gyri tips to echo the
 * knowledge-graph theme. Renders boxless so it can float over the animated
 * particle background like the hero reference.
 *
 * lucide-react renders any `children` *inside* the same <svg>, so the gradient
 * <defs> and the node <circle>s live in the icon's own 24×24 user space and the
 * `color="url(#…)"` stroke resolves locally.
 */

const GLOW = {
  sm: "drop-shadow(0 0 4px rgba(124,140,250,0.55)) drop-shadow(0 0 9px rgba(240,101,149,0.35))",
  md: "drop-shadow(0 0 7px rgba(124,140,250,0.6)) drop-shadow(0 0 16px rgba(240,101,149,0.4))",
  lg: "drop-shadow(0 0 11px rgba(124,140,250,0.65)) drop-shadow(0 0 28px rgba(240,101,149,0.45))",
} as const;

// Node dots sit on the rounded gyri tips of the lucide `Brain` glyph
// (coordinates in its 24×24 user space).
const NODES: Array<[number, number]> = [
  [6, 5.1],
  [18, 5.1],
  [3.6, 10.85],
  [20.4, 10.85],
];

interface BrainMarkProps {
  /** Tailwind sizing (w-* h-*) and any extra classes. */
  className?: string;
  /** Glow intensity — larger marks want a stronger bloom. */
  glow?: keyof typeof GLOW;
  /** Unique gradient id, so multiple marks on one page never collide. */
  gradientId?: string;
  strokeWidth?: number;
  /** Show the accent nodes on the gyri tips (off looks cleaner at tiny sizes). */
  nodes?: boolean;
}

export const BrainMark: React.FC<BrainMarkProps> = ({
  className = "w-24 h-24",
  glow = "lg",
  gradientId = "brainGradient",
  strokeWidth = 1.5,
  nodes = true,
}) => {
  return (
    <Brain
      className={className}
      color={`url(#${gradientId})`}
      strokeWidth={strokeWidth}
      style={{ filter: GLOW[glow] }}
      role="img"
      aria-label="MemoryVerse"
    >
      <defs>
        <linearGradient
          id={gradientId}
          x1="2"
          y1="3"
          x2="22"
          y2="21"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0%" stopColor="#5c7cfa" />
          <stop offset="50%" stopColor="#9d7bf5" />
          <stop offset="100%" stopColor="#f06595" />
        </linearGradient>
      </defs>
      {nodes &&
        NODES.map(([cx, cy]) => (
          <circle
            key={`${cx}-${cy}`}
            cx={cx}
            cy={cy}
            r={0.85}
            fill="#ede9fe"
            stroke="none"
          />
        ))}
    </Brain>
  );
};

export default BrainMark;
