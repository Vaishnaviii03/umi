"use client";

import { UMI_STATE_LABELS, useUmi, type UmiStateKey } from "../hooks/useUmiState";

const STATE_DOT: Record<UmiStateKey, string> = {
  BOOTING: "bg-holo-dim",
  READY: "bg-holo-cyan",
  LISTENING: "bg-holo-magenta",
  THINKING: "bg-holo-purple",
  SPEAKING: "bg-holo-magenta",
  EXECUTING: "bg-holo-cyan",
  ERROR: "bg-holo-danger",
  GREETING: "bg-holo-cyan",
};

/**
 * Minimal top-of-screen presence line: brand + live state + a tiny status dot.
 */
export default function StatusIndicator() {
  const { state, error } = useUmi();
  const label = UMI_STATE_LABELS[state];
  const dot = STATE_DOT[state];

  return (
    <header className="flex select-none items-center justify-between px-6 py-4">
      <div className="flex items-baseline gap-2 text-holo-ink">
        <span className="font-mono text-sm font-semibold tracking-[0.42em]">Umi</span>
        <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-holo-dim">
          companion
        </span>
      </div>

      <div className="flex items-center gap-2.5">
        {error && (
          <span className="max-w-[220px] truncate font-mono text-[10px] text-holo-danger">
            {error}
          </span>
        )}
        <span className={`h-1.5 w-1.5 rounded-full ${dot} shadow-[0_0_10px_currentColor]`} />
        <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-holo-muted">
          {label}
        </span>
      </div>
    </header>
  );
}