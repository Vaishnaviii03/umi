"use client";

import type { UmiStateKey } from "../hooks/useUmiState";

/**
 * The Umi presence itself — the glowing holographic orbs with orbiting rings.
 * Pure presentation; behaviour is driven entirely by `data-state`.
 */
export default function UmiOrb({ state }: { state: UmiStateKey }) {
  const speaking = state === "SPEAKING";

  return (
    <div className="umi-orb" role="img" aria-label={`Umi core — ${state.toLowerCase()}`}>
      <div className="umi-orb__glow" />
      <div className="umi-orb__ring holo-ring holo-ring--inner" style={{ inset: "-6%" }} />
      <div className="umi-orb__core" />

      {speaking && (
        <div className="absolute inset-auto left-1/2 top-[116%] -translate-x-1/2">
          <div className="umi-eq">
            <span style={{ animationDelay: "0ms" }} />
            <span style={{ animationDelay: "120ms" }} />
            <span style={{ animationDelay: "240ms" }} />
            <span style={{ animationDelay: "160ms" }} />
            <span style={{ animationDelay: "320ms" }} />
          </div>
        </div>
      )}

      <div className="umi-orb__halo" />
      <div className="umi-orb__halo umi-orb__halo--rev" />
    </div>
  );
}