"use client";

import React from "react";

/**
 * AetherBackground — an animated particle-network canvas used as a full-viewport
 * background. Adapted from the "Aether Flow" hero into a reusable, themeable
 * background so page content (e.g. the MemoryVerse home hero) can sit on top.
 *
 * - Renders a `fixed inset-0` transparent canvas (clears each frame) so the app's
 *   own dark background shows through and stays consistent with the rest of the UI.
 * - Themed to the MemoryVerse palette (primary blue / accent pink) by default.
 * - Reacts to the pointer (particles gently repel, nearby links brighten).
 * - Respects `prefers-reduced-motion`: draws a single static frame, no animation.
 */

export interface AetherBackgroundProps {
  /** Extra classes for the canvas (e.g. to change z-index or opacity). */
  className?: string;
  /** Particle fill colors, sampled at random per particle. */
  colors?: string[];
  /** Base RGB triplet (no alpha) for connecting lines, e.g. "116, 143, 252". */
  lineColor?: string;
  /** Line color used for links near the pointer, e.g. "255, 255, 255". */
  hoverLineColor?: string;
  /** Larger divisor = fewer particles. Particle count = area / density. */
  density?: number;
  /** Hard cap on particle count (perf guard on large screens). */
  maxParticles?: number;
}

interface Mouse {
  x: number | null;
  y: number | null;
  radius: number;
}

const AetherBackground: React.FC<AetherBackgroundProps> = ({
  className = "",
  colors = [
    "rgba(116, 143, 252, 0.85)", // primary-400 (blue)
    "rgba(145, 167, 255, 0.80)", // primary-300 (light blue)
    "rgba(247, 131, 172, 0.70)", // accent-400 (pink)
  ],
  lineColor = "116, 143, 252",
  hoverLineColor = "226, 232, 255",
  density = 12000,
  maxParticles = 130,
}) => {
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    let animationFrameId = 0;
    let particles: Particle[] = [];
    let lastWidth = window.innerWidth;
    const mouse: Mouse = { x: null, y: null, radius: 180 };

    class Particle {
      x: number;
      y: number;
      directionX: number;
      directionY: number;
      size: number;
      color: string;

      constructor(
        x: number,
        y: number,
        directionX: number,
        directionY: number,
        size: number,
        color: string
      ) {
        this.x = x;
        this.y = y;
        this.directionX = directionX;
        this.directionY = directionY;
        this.size = size;
        this.color = color;
      }

      draw() {
        if (!ctx) return;
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2, false);
        ctx.fillStyle = this.color;
        ctx.fill();
      }

      update() {
        if (this.x > canvas!.width || this.x < 0) {
          this.directionX = -this.directionX;
        }
        if (this.y > canvas!.height || this.y < 0) {
          this.directionY = -this.directionY;
        }

        // Gentle repulsion away from the pointer.
        if (mouse.x !== null && mouse.y !== null) {
          const dx = mouse.x - this.x;
          const dy = mouse.y - this.y;
          const distance = Math.sqrt(dx * dx + dy * dy);
          if (distance < mouse.radius + this.size && distance > 0) {
            const forceDirectionX = dx / distance;
            const forceDirectionY = dy / distance;
            const force = (mouse.radius - distance) / mouse.radius;
            this.x -= forceDirectionX * force * 4;
            this.y -= forceDirectionY * force * 4;
          }
        }

        this.x += this.directionX;
        this.y += this.directionY;
        this.draw();
      }
    }

    const init = () => {
      particles = [];
      const count = Math.min(
        maxParticles,
        Math.floor((canvas.height * canvas.width) / density)
      );
      for (let i = 0; i < count; i++) {
        const size = Math.random() * 2 + 1;
        const x = Math.random() * (canvas.width - size * 4) + size * 2;
        const y = Math.random() * (canvas.height - size * 4) + size * 2;
        const directionX = Math.random() * 0.4 - 0.2;
        const directionY = Math.random() * 0.4 - 0.2;
        const color = colors[Math.floor(Math.random() * colors.length)];
        particles.push(
          new Particle(x, y, directionX, directionY, size, color)
        );
      }
    };

    const connect = () => {
      if (!ctx) return;
      // Squared-distance threshold scales with the viewport size.
      const linkDistSq = (canvas.width / 7) * (canvas.height / 7);
      for (let a = 0; a < particles.length; a++) {
        for (let b = a + 1; b < particles.length; b++) {
          const dxp = particles[a].x - particles[b].x;
          const dyp = particles[a].y - particles[b].y;
          const distSq = dxp * dxp + dyp * dyp;

          if (distSq < linkDistSq) {
            const opacity = 1 - distSq / linkDistSq;

            let nearMouse = false;
            if (mouse.x !== null && mouse.y !== null) {
              const dmx = particles[a].x - mouse.x;
              const dmy = particles[a].y - mouse.y;
              nearMouse =
                dmx * dmx + dmy * dmy < mouse.radius * mouse.radius;
            }

            ctx.strokeStyle = nearMouse
              ? `rgba(${hoverLineColor}, ${opacity})`
              : `rgba(${lineColor}, ${opacity * 0.7})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(particles[a].x, particles[a].y);
            ctx.lineTo(particles[b].x, particles[b].y);
            ctx.stroke();
          }
        }
      }
    };

    const drawFrame = (withMotion: boolean) => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (let i = 0; i < particles.length; i++) {
        if (withMotion) {
          particles[i].update();
        } else {
          particles[i].draw();
        }
      }
      connect();
    };

    const animate = () => {
      animationFrameId = window.requestAnimationFrame(animate);
      drawFrame(true);
    };

    const resizeCanvas = () => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      canvas.width = w;
      canvas.height = h;
      // Regenerate particles only on a real width change (or first run). Mobile
      // browsers fire resize when the URL bar shows/hides — that changes only
      // height, and re-seeding there would make the whole field flicker.
      if (particles.length === 0 || w !== lastWidth) {
        init();
      }
      lastWidth = w;
      if (prefersReducedMotion) drawFrame(false);
    };

    const handleMouseMove = (event: MouseEvent) => {
      mouse.x = event.clientX;
      mouse.y = event.clientY;
    };

    const handleMouseOut = () => {
      mouse.x = null;
      mouse.y = null;
    };

    // Touch support so the effect is interactive on phones/tablets too.
    const handleTouchMove = (event: TouchEvent) => {
      if (event.touches.length > 0) {
        mouse.x = event.touches[0].clientX;
        mouse.y = event.touches[0].clientY;
      }
    };

    const handleTouchEnd = () => {
      mouse.x = null;
      mouse.y = null;
    };

    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);

    if (prefersReducedMotion) {
      drawFrame(false);
    } else {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseout", handleMouseOut);
      window.addEventListener("touchmove", handleTouchMove, { passive: true });
      window.addEventListener("touchend", handleTouchEnd);
      animate();
    }

    return () => {
      window.removeEventListener("resize", resizeCanvas);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseout", handleMouseOut);
      window.removeEventListener("touchmove", handleTouchMove);
      window.removeEventListener("touchend", handleTouchEnd);
      window.cancelAnimationFrame(animationFrameId);
    };
  }, [colors, lineColor, hoverLineColor, density, maxParticles]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={`fixed inset-0 -z-0 h-full w-full pointer-events-none ${className}`}
    />
  );
};

export default AetherBackground;
