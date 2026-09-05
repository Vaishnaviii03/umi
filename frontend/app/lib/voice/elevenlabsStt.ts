import { VOICE_CONNECTION_LOST, type SttCallbacks, type SttController } from "./stt";

const STT_MODEL_ID = "scribe_v2_realtime";

/**
 * ElevenLabs Scribe realtime STT. The backend mints a short-lived single-use
 * token (POST /stt/token) so the real API key never reaches the browser.
 * Scribe.connect() is constructed here via a dynamic import so browser globals
 * inside @elevenlabs/client are never touched during server-side rendering.
 */
export async function createElevenLabsStt(
  token: string,
  callbacks: SttCallbacks,
): Promise<SttController> {
  const { Scribe, RealtimeEvents, CommitStrategy } = await import("@elevenlabs/client");

  const connection = Scribe.connect({
    token,
    modelId: STT_MODEL_ID,
    commitStrategy: CommitStrategy.VAD,
    vadSilenceThresholdSecs: 0.8,
    vadThreshold: 0.3,
    minSpeechDurationMs: 150,
    noVerbatim: true,
    filterBackgroundAudio: true,
    enableLogging: false,
    microphone: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  connection.on(RealtimeEvents.SESSION_STARTED, () => {});
  connection.on(RealtimeEvents.PARTIAL_TRANSCRIPT, (data) => {
    callbacks.onPartial(data?.text ?? "");
  });
  connection.on(RealtimeEvents.COMMITTED_TRANSCRIPT, (data) => {
    callbacks.onCommitted(data?.text ?? "");
  });
  connection.on(RealtimeEvents.ERROR, () => callbacks.onError(VOICE_CONNECTION_LOST));
  connection.on(RealtimeEvents.AUTH_ERROR, () => callbacks.onError(VOICE_CONNECTION_LOST));

  return {
    begin: async () => {
      // Scribe.connect() starts microphone streaming immediately.
    },
    pause: async () => connection.mute(),
    resume: async () => connection.unmute(),
    end: async () => connection.close(),
  };
}