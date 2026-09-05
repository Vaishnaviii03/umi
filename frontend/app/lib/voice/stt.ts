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
};

export const VOICE_CONNECTION_LOST = "Voice connection lost.";