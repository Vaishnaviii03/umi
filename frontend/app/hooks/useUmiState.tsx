"use client";

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";

/**
 * Centralized visual state model for the Umi presence.
 *
 * No scattered boolean flags — every visual layer (orbit, scene, indicators)
 * reads from this single stream of states.
 */
export type UmiStateKey =
  | "BOOTING"
  | "READY"
  | "LISTENING"
  | "THINKING"
  | "SPEAKING"
  | "EXECUTING"
  | "ERROR"
  | "GREETING";

export const UMI_STATE_LABELS: Record<UmiStateKey, string> = {
  BOOTING: "Bringing Umi online",
  READY: "Ready",
  LISTENING: "Listening",
  THINKING: "Thinking",
  SPEAKING: "Speaking",
  EXECUTING: "Executing",
  ERROR: "Attention needed",
  GREETING: "Greeting",
};

type UmiContextValue = {
  state: UmiStateKey;
  error: string | null;
  transition: (next: UmiStateKey) => void;
  fail: (message: string) => void;
  clearError: () => void;
  beginListening: () => void;
  endListening: () => void;
  /** Mark the Umi presence as "speaking" briefly. Reserved for the future
   *  TTS pipeline; the chat surface uses it as a reply-arrival cue today. */
  speak: (durationMs?: number) => void;
  /** Transition to GREETING state and optionally provide greeting text */
  greet: (text?: string) => void;
  /** Mark greeting as complete, transition to READY */
  endGreeting: () => void;
};

const UmiStateContext = createContext<UmiContextValue | null>(null);

const ERROR_AUTO_RECOVER_MS = 5000;

export function UmiProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<UmiStateKey>("READY");
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | undefined>(undefined);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== undefined) {
      window.clearTimeout(timerRef.current);
      timerRef.current = undefined;
    }
  }, []);

  const transition = useCallback(
    (next: UmiStateKey) => {
      clearTimer();
      setState(next);
      if (next !== "ERROR") setError(null);
    },
    [clearTimer],
  );

  const fail = useCallback(
    (message: string) => {
      clearTimer();
      setError(message);
      setState("ERROR");
      timerRef.current = window.setTimeout(() => {
        setError(null);
        setState("READY");
      }, ERROR_AUTO_RECOVER_MS);
    },
    [clearTimer],
  );

const clearError = useCallback(() => {
    clearTimer();
    setError(null);
    setState("READY");
  }, [clearTimer]);

  const beginListening = useCallback(() => {
    transition("LISTENING");
  }, [transition]);

  const endListening = useCallback(() => {
    transition("READY");
  }, [transition]);

  const speak = useCallback(
    (durationMs = 900) => {
      transition("SPEAKING");
      timerRef.current = window.setTimeout(() => {
        setState("READY");
      }, durationMs);
    },
    [transition],
  );

  const greet = useCallback(
    (text?: string) => {
      // Store greeting text in sessionStorage for components that need it
      if (text) {
        sessionStorage.setItem("umi_greeting_text", text);
      }
      transition("GREETING");
    },
    [transition],
  );

  const endGreeting = useCallback(() => {
    transition("READY");
  }, [transition]);

  return (
    <UmiStateContext.Provider
      value={{
        state,
        error,
        transition,
        fail,
        clearError,
        beginListening,
        endListening,
        speak,
        greet,
        endGreeting,
      }}
    >
      {children}
    </UmiStateContext.Provider>
  );
}

export function useUmi() {
  const ctx = useContext(UmiStateContext);
  if (!ctx) throw new Error("useUmi must be used within <UmiProvider>");
  return ctx;
}