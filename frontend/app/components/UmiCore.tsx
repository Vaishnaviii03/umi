"use client";

import type { UmiStateKey } from "../hooks/useUmiState";
import UmiOrb from "./UmiOrb";

/**
 * Full presence mount: vertical beam + platform handled by the scene; this
 * hosts the orb and attaches the state-driven behaviour via `data-state`.
 */
export default function UmiCore({ state }: { state: UmiStateKey }) {
  return (
    <div
      className="umi-core relative flex h-[42vh] items-center justify-center"
      data-state={state}
      aria-hidden
    >
      {state === "LISTENING" && <span className="umi-ripple" />}
      <UmiOrb state={state} />
    </div>
  );
}