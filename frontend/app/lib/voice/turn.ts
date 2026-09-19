/**
 * Pure helpers for the continuous voice session. Kept free of React/DOM or
 * network concerns so they can be unit-tested without a browser.
 */

export const MIN_TRANSCRIPT_CHARS = 1;

export function normalizeTranscript(text: string): string {
  return (text ?? "").replace(/\s+/g, " ").trim();
}

export function isMeaningfulTranscript(text: string): boolean {
  return normalizeTranscript(text).length >= MIN_TRANSCRIPT_CHARS;
}

/**
 * Detect a repeat of the same utterance. STT providers can re-emit the
 * committed transcript for the same spoken segment (e.g. after a reconnect),
 * which must not trigger a duplicate reply.
 */
export function isDuplicateCommit(previous: string, next: string): boolean {
  const prev = normalizeTranscript(previous).toLowerCase();
  const nextText = normalizeTranscript(next).toLowerCase();
  if (!prev || !nextText) return false;
  if (prev === nextText) return true;
  const shorter = Math.min(prev.length, nextText.length);
  const longer = Math.max(prev.length, nextText.length);
  if (shorter / longer >= 0.8 && (prev.startsWith(nextText) || nextText.startsWith(prev))) {
    return true;
  }
  return false;
}

const INTERRUPT_SET = new Set([
  "stop",
  "umi stop",
  "stop umi",
  "stop please",
  "please stop",
  "wait",
  "umi wait",
  "wait umi",
  "hold on",
  "umi hold on",
  "hold on umi",
  "pause",
  "pause umi",
  "umi pause",
  "quiet",
  "be quiet",
  "shut up",
  "shh",
  "stop it",
  "stop now",
  "stop talking",
  "stop speaking",
]);

/**
 * Identify voice interruption commands (e.g. "stop", "umi stop", "wait", "hold on")
 * to immediately cut off speech playback and acknowledge Boss.
 */
export function isInterruptionPhrase(text: string): boolean {
  const cleaned = (text ?? "")
    .toLowerCase()
    .replace(/[^a-z\s]/g, "")
    .trim()
    .replace(/\s+/g, " ");
  if (!cleaned) return false;
  if (INTERRUPT_SET.has(cleaned)) return true;
  const words = cleaned.split(" ");
  if (words.length <= 4) {
    if (
      words.includes("stop") ||
      (words.includes("hold") && words.includes("on")) ||
      words.includes("pause") ||
      words.includes("wait")
    ) {
      return true;
    }
  }
  return false;
}