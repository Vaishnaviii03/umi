import { VOICE_CONNECTION_LOST, type SttCallbacks, type SttController } from "./stt";

type AnySpeechRecognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: unknown) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
};

type SpeechRecognitionResultLike = {
  isFinal: boolean;
  length: number;
  [index: number]: { transcript: string };
};

declare global {
  var webkitSpeechRecognition: (new () => AnySpeechRecognition) | undefined;
}

export function isWebSpeechSupported(): boolean {
  return typeof webkitSpeechRecognition !== "undefined";
}

/**
 * Browser Web Speech API fallback used when ElevenLabs STT is unavailable.
 * The recognition engine is kept alive across pauses by restarting it after
 * `end`/pause events, which keeps the one-click session continuous.
 */
export function createWebSpeechStt(callbacks: SttCallbacks): SttController {
  const Recognition = globalThis.webkitSpeechRecognition;
  if (!Recognition) {
    throw new Error("speech-not-supported");
  }

  let recognition: AnySpeechRecognition | null = null;
  let running = false;

  const pushResult = (event: { resultIndex: number; results: SpeechRecognitionResultLike[] }) => {
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      const text = result[0]?.transcript ?? "";
      if (result.isFinal) {
        callbacks.onCommitted(text);
      } else {
        callbacks.onPartial(text);
      }
    }
  };

  const spawn = () => {
    if (recognition) return recognition;
    const rec = new Recognition();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.onresult = pushResult as AnySpeechRecognition["onresult"];
    rec.onerror = (event) => {
      if (event.error && event.error !== "no-speech" && event.error !== "aborted") {
        callbacks.onError(VOICE_CONNECTION_LOST);
      }
    };
    rec.onend = () => {
      // The session asked us to keep listening: restart transparently.
      if (running) {
        try {
          recognition?.start();
        } catch {
          // Recognition already started — ignore.
        }
      }
    };
    recognition = rec;
    return rec;
  };

  const startRecognition = () => {
    running = true;
    const rec = spawn();
    try {
      rec.start();
    } catch {
      // Already started — ignore.
    }
  };

  return {
    begin: async () => startRecognition(),
    pause: async () => {
      running = false;
      recognition?.stop();
    },
    resume: async () => startRecognition(),
    end: async () => {
      running = false;
      const rec = recognition;
      recognition = null;
      rec?.abort();
    },
  };
}