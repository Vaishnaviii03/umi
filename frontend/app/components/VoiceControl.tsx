"use client";

import type { VoiceMode } from "../hooks/useVoiceSession";

type VoiceControlProps = {
  active: boolean;
  mode: VoiceMode | null;
  onToggle: () => void;
};

/**
 * One-click start/stop for the continuous voice session. When idle it shows a
 * mic with a "Start" affordance; once the session is live it becomes a square
 * "Stop" control with a stronger holo glow and the active STT provider tag.
 */
export default function VoiceControl({ active, mode, onToggle }: VoiceControlProps) {
  return (
    <button
      type="button"
      aria-label={active ? "Stop voice session" : "Start voice session"}
      title={active ? "Stop continuous voice conversation" : "Start continuous voice conversation"}
      onClick={onToggle}
      className={`group relative flex h-9 shrink-0 cursor-pointer items-center gap-1.5 rounded-full border pl-1.5 pr-2.5 font-mono text-[10px] tracking-widest uppercase transition-all duration-300 ${
        active
          ? "border-holo-magenta bg-holo-magenta/15 text-holo-magenta shadow-[0_0_22px_rgba(232,121,249,0.5)]"
          : "border-holo-border text-holo-muted hover:border-holo-border-strong hover:text-holo-magenta"
      }`}
    >
      <span
        className={`grid h-6 w-6 place-items-center rounded-full ${
          active ? "bg-holo-magenta/25" : "bg-holo-panel/60 group-hover:bg-holo-magenta/10"
        }`}
      >
        {active ? (
          <svg viewBox="0 0 24 24" className="h-3 w-3" fill="currentColor" stroke="currentColor" strokeWidth="1.8">
            <rect x="7" y="7" width="10" height="10" rx="1.5" strokeLinecap="round" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.7">
            <rect x="9" y="3" width="6" height="11" rx="3" strokeLinecap="round" />
            <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" strokeLinecap="round" />
          </svg>
        )}
      </span>
      <span className="select-none">{active ? "Stop" : "Start"}</span>
      {active && mode && <span className="pr-0.5 text-[9px] text-holo-muted">{mode === "elevenlabs" ? "11L" : "WEB"}</span>}
    </button>
  );
}