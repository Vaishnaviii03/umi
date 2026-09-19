/**
 * The one, stable contract the session controller (useVoiceSession) uses to
 * talk to any speech-to-text provider. Implementations:
 *  - ElevenLabs Scribe realtime (via @elevenlabs/client, backend-minted token)
 *  - Browser Web Speech API fallback
 */

export type SttCallbacks = {
  onPartial: (text: string) => void;
  onCommitted: (text: string) => void;
  onError: (message: string) => void;
};

export type SttController = {
  /** Fully activate listening (called once after construction). */
  begin: () => Promise<void>;
  /** Pause listening but keep the session alive (Umi is speaking). */
  pause: () => Promise<void>;
  /** Resume listening after a pause. */
  resume: () => Promise<void>;
  /** Tear the whole session down. */
  end: () => Promise<void>;
  /** Enable/disable barge-in mode: when enabled, STT stays active but only reports meaningful speech for interruption detection. */
  setBargeInMode?: (enabled: boolean) => void;
};

export const VOICE_CONNECTION_LOST = "Voice connection lost.";

export const VOICE_CREDITS_EXHAUSTED =
  "Umi's voice credits have run out — text chat still works.";

/**
 * Map a provider error payload to a user-facing message.
 * Provider quota/billing rejections get an accurate, actionable message;
 * everything else stays the generic connection-lost string.
 */
export function mapSttErrorMessage(detail: unknown): string {
  const d = detail as { message_type?: string; error?: string } | null | undefined;
  const raw = `${d?.message_type ?? ""} ${d?.error ?? ""}`.toLowerCase();
  const quotaLike =
    d?.message_type === "quota_exceeded" ||
    /quota|credit|funds|billing|insufficient|charge/i.test(raw);
  return quotaLike ? VOICE_CREDITS_EXHAUSTED : VOICE_CONNECTION_LOST;
}