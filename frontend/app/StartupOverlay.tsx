"use client";

import { useEffect, useState, type ReactNode } from "react";

type StartupPayload = {
  state: string;
  greeting: string | null;
  context: Record<string, unknown>;
  softErrors: { state: string; message: string }[];
};

const STATE_LABELS: Record<string, string> = {
  LAUNCHING: "Launching Umi…",
  INITIALIZING: "Initializing systems…",
  LOADING_CONTEXT: "Loading context…",
  READY_TO_GREET: "Getting ready…",
  GREETING: "Greeting…",
  STARTUP_MEDIA: "Starting media…",
  READY: "Ready",
  INITIALIZATION_ERROR: "Startup issue",
  MEDIA_ERROR: "Media not available",
  DATABASE_ERROR: "Database not available",
  LLM_ERROR: "Reasoning engine not ready",
  VOICE_ERROR: "Voice not available",
  PERMISSION_ERROR: "Permission not available",
};

export default function StartupOverlay({ children }: { children: ReactNode }) {
  const [payload, setPayload] = useState<StartupPayload | null>(null);
  const [noBridge, setNoBridge] = useState(false);

  useEffect(() => {
    const bridge = (window as unknown as { umi?: { onStartupState: (cb: (p: StartupPayload) => void) => void } }).umi;

    if (!bridge) {
      // Plain browser (dev mode without the desktop shell) — there is no startup
      // stream, so fall back to the normal UI after a short transition.
      const timer = setTimeout(() => setNoBridge(true), 1500);
      return () => clearTimeout(timer);
    }

    bridge.onStartupState(setPayload);
  }, []);

  if (noBridge || payload?.state === "READY") return <>{children}</>;

  const label = STATE_LABELS[payload?.state ?? "LAUNCHING"] ?? "Starting Umi…";
  const greeting = payload?.greeting;
  const errorState = Boolean(payload?.state?.endsWith("_ERROR"));

  return (
    <div className="relative flex h-dvh w-full flex-col items-center justify-center gap-7 overflow-hidden bg-holo-bg px-6 text-center text-holo-ink">
      <div className="holo-beacon" style={{ width: "38vmax", height: "38vmax", background: "radial-gradient(circle, rgba(168,100,255,0.2), transparent 70%)" }} />
      <div className="holo-beam" />

      <div className="relative">
        <div className="umi-orb" style={{ width: 150, height: 150, minWidth: 150, minHeight: 150 }}>
          <div className="umi-orb__glow" />
          <div className="umi-orb__core" />
          <div className="umi-orb__halo" style={{ animation: errorState ? "none" : undefined }} />
          <div className="umi-orb__halo umi-orb__halo--rev" style={{ animation: errorState ? "none" : undefined }} />
        </div>
      </div>

      <div className="relative">
        <div className="font-mono text-sm font-semibold tracking-[0.5em]">Umi</div>
        <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.4em] text-holo-dim">personal companion</div>
      </div>

      {greeting && <p className="relative text-lg text-holo-soft">{greeting}</p>}

      {errorState ? (
        <p className="relative max-w-md text-sm text-holo-danger">
          {label}
          <span className="text-holo-dim"> Check the desktop shell logs for details.</span>
        </p>
      ) : (
        <div className="relative flex flex-col items-center gap-3">
          <div className="h-1.5 w-40 overflow-hidden rounded-full border border-holo-border bg-white/[0.04]">
            <div className="h-full w-1/3 animate-pulse rounded-full bg-gradient-to-r from-holo-violet to-holo-magenta" />
          </div>
          <p className="text-sm tracking-wide text-holo-muted">{label}</p>
        </div>
      )}

      {payload?.softErrors.length ? (
        <p className="relative max-w-md text-xs text-holo-dim">
          {payload.softErrors.map((e) => `[${e.state}] ${e.message}`).join(" · ")}
        </p>
      ) : null}
    </div>
  );
}