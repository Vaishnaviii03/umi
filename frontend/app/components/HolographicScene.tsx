"use client";

import { useEffect, useRef } from "react";
import type { UmiStateKey } from "../hooks/useUmiState";

type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  hue: number;
  baseAlpha: number;
  phase: number;
  speed: number;
  size: number;
};

function buildParticles(count: number, w: number, h: number): Particle[] {
  const coreX = w / 2;
  const coreY = h * 0.36;
  const bandW = w * 0.72;
  const bandH = h * 0.72;
  return Array.from({ length: count }, () => ({
    // Clustered around the central presence so the core feels surrounded.
    x: coreX + (Math.random() - 0.5) * bandW,
    y: coreY + (Math.random() - 0.5) * bandH,
    vx: (Math.random() - 0.5) * 0.16,
    vy: (Math.random() - 0.5) * 0.16,
    r: 0.6 + Math.random() * 1.6,
    hue: 272 + Math.random() * 40, // violet -> magenta
    baseAlpha: 0.15 + Math.random() * 0.6,
    phase: Math.random() * Math.PI * 2,
    speed: 0.4 + Math.random() * 1.1,
    size: 1,
  }));
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/**
 * Layered holographic backdrop: ambient halos, concentric rings, a projection
 * platform, a faint grid floor and a lightweight canvas particle field driven
 * by the Umi state.
 */
export default function HolographicScene({ state }: { state: UmiStateKey }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef(state);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let raf = 0;
    let w = 0;
    let h = 0;
    let particles: Particle[] = [];

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      w = rect.width;
      h = rect.height;
      canvas.width = Math.max(1, Math.floor(w * dpr));
      canvas.height = Math.max(1, Math.floor(h * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const target = Math.min(190, Math.max(60, Math.floor((w * h) / 11000)));
      particles = buildParticles(target, w, h);
    };

    const draw = (now: number) => {
      const st = stateRef.current;
      const t = now / 1000;
      const cx = w / 2;
      const cy = h * 0.4;
      ctx.clearRect(0, 0, w, h);
      ctx.globalCompositeOperation = "lighter";

      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;

        const dx = p.x - cx;
        const dy = p.y - cy;
        const dist = Math.hypot(dx, dy) || 1;
        const pull = st === "THINKING" ? 0.012 : st === "EXECUTING" ? 0.006 : 0;

        if (pull > 0) {
          p.vx -= (dx / dist) * pull * 0.4;
          p.vy -= (dy / dist) * pull * 0.4;
        } else {
          p.vx += (Math.random() - 0.5) * 0.012;
          p.vy += (Math.random() - 0.5) * 0.012;
        }
        p.vx = clamp(p.vx, -0.35, 0.35);
        p.vy = clamp(p.vy, -0.35, 0.35);

        if (p.x < -8) p.x = w + 8;
        if (p.x > w + 8) p.x = -8;
        if (p.y < -8) p.y = h + 8;
        if (p.y > h + 8) p.y = -8;

        const breathing = 0.55 + 0.45 * Math.sin(t * p.speed + p.phase);
        const listening = st === "LISTENING";
        const ripples = listening ? Math.sin(t * 2.4 + p.phase) * 0.4 : 0;
        let alpha = p.baseAlpha * breathing + ripples * 0.25;
        if (st === "THINKING") alpha = clamp(alpha * 1.3, 0, 1);
        if (st === "ERROR") alpha = clamp(alpha * 0.5, 0, 1);

        const pulseRadius = st === "LISTENING" ? p.r * (1 + 0.9 * Math.abs(ripples)) : p.r;
        ctx.beginPath();
        ctx.arc(p.x, p.y, pulseRadius, 0, Math.PI * 2);
        ctx.fillStyle = `hsla(${p.hue}, 92%, ${listening ? 74 : 66}%, ${clamp(alpha, 0, 1)})`;
        ctx.fill();
      }

      // Concentric listening ripples drawn on canvas for extra clarity
      if (stateRef.current === "LISTENING") {
        const ringR = 46 + ((t * 60) % 120);
        ctx.beginPath();
        ctx.arc(cx, cy, ringR, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(232, 121, 249, ${0.4 * (1 - ringR / 170)})`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      if (reduced) return;
      raf = requestAnimationFrame(draw);
    };

    resize();
    const onResize = () => resize();
    window.addEventListener("resize", onResize);

    if (reduced) {
      draw(performance.now());
    } else {
      raf = requestAnimationFrame(draw);
    }

    return () => {
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      {/* Ambient depth */}
      <div
        className="holo-beacon"
        style={{
          width: "46vmax",
          height: "46vmax",
          left: "-10vmax",
          top: "-14vmax",
          background: "radial-gradient(circle, rgba(124,58,237,0.22), transparent 70%)",
        }}
      />
      <div
        className="holo-beacon"
        style={{
          width: "40vmax",
          height: "40vmax",
          right: "-12vmax",
          bottom: "-10vmax",
          background: "radial-gradient(circle, rgba(232,121,249,0.16), transparent 70%)",
        }}
      />

      {/* Vertical presence + projection platform */}
      <div className="holo-layer">
        <div className="holo-beam" />
        <div className="holo-platform">
          <div className="holo-platform__ring" style={{ inset: "4%" }} />
          <div
            className="holo-platform__ring"
            style={{ inset: "12%", borderColor: "rgba(168,100,255,0.14)" }}
          />
          <div
            className="holo-platform__ring"
            style={{ inset: "22%", borderColor: "rgba(168,100,255,0.1)" }}
          />
        </div>
        <div className="holo-grid" />
      </div>

      {/* Particle field */}
      <canvas ref={canvasRef} className="absolute inset-0" />

      {/* Subtle concentric rings around the whole presence */}
      {[16, 27, 40].map((size) => (
        <div
          key={size}
          className="holo-ring"
          style={{
            width: `${size}vmin`,
            height: `${size}vmin`,
            left: `calc(50% - ${size / 2}vmin)`,
            top: `calc(40% - ${size / 2}vmin)`,
          }}
        />
      ))}

      {/* Vignette + scanline */}
      <div className="holo-vignette" />
    </div>
  );
}