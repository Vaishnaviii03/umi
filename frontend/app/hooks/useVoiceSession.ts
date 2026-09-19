"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createElevenLabsStt } from "../lib/voice/elevenlabsStt";
import { isWebSpeechSupported, createWebSpeechStt } from "../lib/voice/webSpeechStt";
import { isDuplicateCommit, isMeaningfulTranscript } from "../lib/voice/turn";
import type { SttCallbacks, SttController } from "../lib/voice/stt";
import { traceLatency } from "../lib/telemetry";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export type VoiceMode = "elevenlabs" | "webspeech";

export type VoiceSessionApi = {
  active: boolean;
  /** Available for synchronous reads inside async flows (state may be stale). */
  activeRef: React.MutableRefObject<boolean>;
  mode: VoiceMode | null;
  partial: string;
  error: string | null;
  startSession: () => Promise<void>;
  stopSession: () => Promise<void>;
  pauseListening: () => Promise<void>;
  resumeListening: () => Promise<void>;
};

/**
 * One-click continuous voice session (STT). This hook owns the speech-to-text
 * lifecycle only — UmiExperience keeps owning the LLM+TTS reply pipeline, so
 * text and voice share the exact same turn flow.
 *
 * Mode selection: ElevenLabs Scribe realtime when the backend can mint a
 * token, transparent fallback to the browser Web Speech API otherwise.
 */
export function useVoiceSession(dependencies: {
  onCommittedText: (text: string) => void;
  onPartialText?: (text: string) => void;
}): VoiceSessionApi {
  const { onCommittedText, onPartialText } = dependencies;
  const onCommittedRef = useRef(onCommittedText);
  const onPartialRef = useRef(onPartialText);

  useEffect(() => {
    onCommittedRef.current = onCommittedText;
    onPartialRef.current = onPartialText;
  }, [onCommittedText, onPartialText]);

  const [active, setActive] = useState(false);
  const activeRef = useRef(false);
  const [mode, setMode] = useState<VoiceMode | null>(null);
  const [partial, setPartial] = useState("");
  const [error, setError] = useState<string | null>(null);

  const controllerRef = useRef<SttController | null>(null);
  const lastCommitRef = useRef("");
  const lastPartialAtRef = useRef(0);
  const failoverRef = useRef(false);

  const stopSession = useCallback(async () => {
    const controller = controllerRef.current;
    controllerRef.current = null;
    activeRef.current = false;
    setActive(false);
    setMode(null);
    setPartial("");
    if (controller) {
      await controller.end();
    }
  }, []);

  const handleError = useCallback(
    (message: string) => {
      setError(message);
      void stopSession();
    },
    [stopSession],
  );

  const startSession = useCallback(async () => {
    if (activeRef.current) return;
    activeRef.current = true;
    setActive(true);
    setError(null);
    setPartial("");
    lastCommitRef.current = "";
    failoverRef.current = false;

    const onPartial = (text: string) => {
      lastPartialAtRef.current = performance.now();
      setPartial(text);
      onPartialRef.current?.(text);
    };
    const onCommitted = (text: string) => {
      if (!isMeaningfulTranscript(text)) return;
      if (isDuplicateCommit(lastCommitRef.current, text)) return;
      if (lastPartialAtRef.current > 0) {
        traceLatency({
          stt_commit_ms: Math.round(performance.now() - lastPartialAtRef.current),
        });
        lastPartialAtRef.current = 0;
      }
      lastCommitRef.current = text;
      setPartial("");
      onCommittedRef.current(text);
    };

    // Terminal error: show the message and tear the whole session down.
    const fatalError = handleError;

    // ElevenLabs provider error handler: transparently hand the live, still-
    // active session over to the browser Web Speech API instead of stopping.
    // One attempt only — if the fallback fails too, surface a real error.
    const failoverOnError = (message: string) => {
      if (failoverRef.current) {
        fatalError(message);
        return;
      }
      if (!isWebSpeechSupported()) {
        fatalError("Voice is unavailable on this device.");
        return;
      }
      failoverRef.current = true;
      const old = controllerRef.current;
      controllerRef.current = null;
      if (old) void old.end();

      const webCallbacks: SttCallbacks = { onPartial, onCommitted, onError: fatalError };
      try {
        const wc = createWebSpeechStt(webCallbacks);
        controllerRef.current = wc;
        void wc.begin();
        setMode("webspeech");
      } catch {
        fatalError("Voice is unavailable on this device.");
      }
    };

    const callbacks: SttCallbacks = { onPartial, onCommitted, onError: failoverOnError };
    const webCallbacks: SttCallbacks = { onPartial, onCommitted, onError: fatalError };

    let controller: SttController | null = null;

    // 1) Prefer ElevenLabs realtime via a backend-minted single-use token.
    try {
      const res = await fetch(`${BACKEND_URL}/stt/token`, { cache: "no-store" });
      if (res.ok) {
        const data = (await res.json()) as { token?: string };
        if (data.token) {
          try {
            controller = await createElevenLabsStt(data.token, callbacks);
            setMode("elevenlabs");
          } catch {
            controller = null;
          }
        }
      }
    } catch {
      controller = null;
    }

    // 2) Transparent fallback to the browser Web Speech API.
    if (!controller) {
      if (!isWebSpeechSupported()) {
        await stopSession();
        setError("Voice is unavailable on this device.");
        return;
      }
      try {
        controller = createWebSpeechStt(webCallbacks);
        setMode("webspeech");
      } catch {
        await stopSession();
        setError("Voice is unavailable on this device.");
        return;
      }
    }

    if (!activeRef.current) {
      // Stop was requested while we were still connecting.
      await controller.end();
      return;
    }

    controllerRef.current = controller;
    await controller.begin();
  }, [handleError, stopSession]);

  const pauseListening = useCallback(async () => {
    await controllerRef.current?.pause();
  }, []);

  const resumeListening = useCallback(async () => {
    await controllerRef.current?.resume();
  }, []);

  return { active, activeRef, mode, partial, error, startSession, stopSession, pauseListening, resumeListening };
}