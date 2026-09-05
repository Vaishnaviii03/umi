/**
 * Pure helpers for the Umi voice (TTS) pipeline. Kept free of React/DOM so
 * they can be unit-tested without a browser.
 */

export const MAX_TTS_CHARS = 4000;

export const VOICE_UNAVAILABLE_MESSAGE = "Voice unavailable — text response ready.";

export const FALLBACK_SPEAK_MS = 900;

export function normalizeTtsText(text: string): string {
  const trimmed = (text ?? "").trim();
  return trimmed.length > MAX_TTS_CHARS ? trimmed.slice(0, MAX_TTS_CHARS) : trimmed;
}

export function isSentenceComplete(text: string): boolean {
  return /[.!?…]$/.test((text ?? "").trim());
}

/**
 * Split running text into sentences on sentence-ending punctuation followed by
 * whitespace. Keeps the punctuation attached to its sentence. A trailing
 * non-terminated fragment stays intact (it is a partial sentence).
 */
export function splitSentences(text: string): string[] {
  const trimmed = (text ?? "").trim();
  if (!trimmed) return [];
  return trimmed
    .split(/(?<=[.!?…])\s+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

/**
 * Given a buffer of streamed text, pop the completed sentences while keeping
 * any trailing partial sentence buffered for the next chunk.
 */
export function popCompletedSentences(buffer: string): {
  complete: string[];
  remainder: string;
} {
  const parts = splitSentences(buffer);
  const complete: string[] = [];
  const remainder: string[] = [];
  for (const part of parts) {
    if (isSentenceComplete(part)) {
      complete.push(part);
    } else {
      remainder.push(part);
    }
  }
  return { complete, remainder: remainder.join(" ") };
}