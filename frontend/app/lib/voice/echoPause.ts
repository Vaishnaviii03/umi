export type EchoPauseState = "live" | "paused";

export interface EchoPauseDecision {
  next: EchoPauseState;
  pause?: boolean;
  resume?: boolean;
}

/** A new turn begins (thinking): the mic may listen again — Umi is silent. */
export function onNewTurn(state: EchoPauseState): EchoPauseDecision {
  if (state === "live") return { next: state };
  return { next: "live", resume: true };
}

/** Umi starts speaking a sentence: mute the mic once, only if voice is active. */
export function onSentenceSpoken(state: EchoPauseState, voiceActive: boolean): EchoPauseDecision {
  if (!voiceActive || state === "paused") return { next: state };
  return { next: "paused", pause: true };
}

/** The turn's last audio finished: listening may resume. */
export function onTurnFinished(state: EchoPauseState): EchoPauseDecision {
  if (state === "live") return { next: state };
  return { next: "live", resume: true };
}