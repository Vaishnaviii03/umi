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