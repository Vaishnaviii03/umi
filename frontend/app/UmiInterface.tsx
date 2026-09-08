"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Conversation from "./components/Conversation";
import HolographicScene from "./components/HolographicScene";
import StatusIndicator from "./components/StatusIndicator";
import TextInput from "./components/TextInput";
import UmiCore from "./components/UmiCore";
import VoiceControl from "./components/VoiceControl";
import MemoriesPanel from "./MemoriesPanel";
import TasksPanel from "./TasksPanel";
import GmailPanel from "./GmailPanel";
import { useChat } from "./hooks/useChat";
import { useTts } from "./hooks/useTts";
import { useVoiceSession } from "./hooks/useVoiceSession";
import { UmiProvider, useUmi } from "./hooks/useUmiState";
import { traceLatency, nowMs } from "./lib/telemetry";
import { VOICE_UNAVAILABLE_MESSAGE } from "./lib/speech";

const VOICE_NOTE_MS = 4000;

/** Normalize text for echo-guard comparison (lowercase, alphanumeric only). */
function normText(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function UmiExperience() {
  const umi = useUmi();
  const [showMemories, setShowMemories] = useState(false);
  const [showTasks, setShowTasks] = useState(false);
  const [showGmail, setShowGmail] = useState(false);
  const [showChat, setShowChat] = useState(true);
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const [greetingText, setGreetingText] = useState<string | null>(null);
  const voiceNoteTimerRef = useRef<number | undefined>(undefined);
  const busyRef = useRef(false);
  const thinking = umi.state === "THINKING";

  // Per-turn streaming control. `turnToken` lets the hook's async stream events
  // (thinking/sentence/done/error) be attributed to the turn that spawned them,
  // so events from an interrupted turn are ignored instead of corrupting state.
  const turnTokenRef = useRef(0);
  const pendingSpeaksRef = useRef(0);
  const streamDoneRef = useRef(false);
  const micPausedRef = useRef(false);
  const voiceNoteShownRef = useRef(false);
  const turnStartAtRef = useRef(0);
  const lastSpokenRef = useRef("");
  const greetedRef = useRef(false);

  const tts = useTts({
    onAudioStart: useCallback(() => {
      // First audio actually started — measure commit/send → first speech.
      if (turnStartAtRef.current > 0) {
        traceLatency({
          total_turn_latency_ms: Math.round(nowMs() - turnStartAtRef.current),
        });
        turnStartAtRef.current = 0;
      }
    }, []),
  });

  const showVoiceNote = useCallback(() => {
    if (voiceNoteShownRef.current) return;
    voiceNoteShownRef.current = true;
    setVoiceNote(VOICE_UNAVAILABLE_MESSAGE);
    if (voiceNoteTimerRef.current !== undefined) {
      window.clearTimeout(voiceNoteTimerRef.current);
    }
    voiceNoteTimerRef.current = window.setTimeout(() => setVoiceNote(null), VOICE_NOTE_MS);
  }, []);

  // Desktop startup greeting — spoke, not just shown. Runs after `tts` exists.
  // Handshake: signal readiness so the desktop replays a GREETING payload that
  // was emitted before Next.js hydrated (otherwise it would be dropped).
  useEffect(() => {
    const umiApi = (window as unknown as {
      umi?: {
        onStartupState?: (callback: (payload: { state: string; greeting?: string }) => void) => (() => void) | void;
        getStartupState?: () => Promise<{ state: string; greeting?: string } | null>;
        notifyStartupReady?: () => void;
      };
    }).umi;

    const handlePayload = (payload: { state: string; greeting?: string }) => {
      if (payload?.state !== "GREETING" || !payload.greeting) return;
      if (greetedRef.current) return;
      greetedRef.current = true;
      setGreetingText(payload.greeting);
      umi.greet(payload.greeting);
      micPausedRef.current = true;
      lastSpokenRef.current = payload.greeting;
      void tts
        .speak(payload.greeting)
        .catch(() => showVoiceNote())
        .finally(() => {
          micPausedRef.current = false;
          umi.endGreeting();
        });
    };

    const cleanup = umiApi?.onStartupState?.(handlePayload);
    if (umiApi?.notifyStartupReady) {
      umiApi.notifyStartupReady();
    }
    // Pull-based fallback: read the current startup state directly in case the
    // push/ACK raced a window reload.
    umiApi?.getStartupState?.().then((p) => {
      if (p) handlePayload(p);
    });
    return () => {
      if (typeof cleanup === "function") cleanup();
    };
  }, [tts, umi, showVoiceNote]);

  const voice = useVoiceSession({ onCommittedText: startTurn });
  const { active, activeRef, mode, partial, error, startSession, stopSession, resumeListening } = voice;

  const finishTurn = useCallback(() => {
    busyRef.current = false;
    micPausedRef.current = false;
    pendingSpeaksRef.current = 0;
    turnStartAtRef.current = 0;
    if (activeRef.current) {
      void resumeListening().then(() => umi.transition("LISTENING"));
    } else {
      umi.transition("READY");
    }
  }, [activeRef, resumeListening, umi]);

  const maybeFinish = useCallback(() => {
    if (busyRef.current && streamDoneRef.current && pendingSpeaksRef.current === 0) {
      finishTurn();
    }
  }, [finishTurn]);

  function startTurn(text: string) {
    const incoming = text.trim();
    if (!incoming) return;
    if (busyRef.current) {
      // Barge-in: the Boss spoke while Umi was thinking/speaking. Ignore an
      // obvious re-capture of Umi's own voice (turns are mostly long once we
      // stream), then interrupt the in-flight turn and start a fresh one.
      const a = normText(incoming);
      const b = normText(lastSpokenRef.current);
      const echo = !!a && !!b && (a.includes(b) || b.includes(a));
      if (echo) return;
      turnTokenRef.current += 1;
      tts.stop();
      chat.cancel();
      pendingSpeaksRef.current = 0;
      streamDoneRef.current = false;
    }
    const token = turnTokenRef.current + 1;
    turnTokenRef.current = token;
    busyRef.current = true;
    turnStartAtRef.current = nowMs();
    void chat.send(incoming, token, activeRef.current);
  }

  const chat = useChat({
    onThinking: (token) => {
      if (token !== turnTokenRef.current) return;
      tts.stop();
      pendingSpeaksRef.current = 0;
      streamDoneRef.current = false;
      micPausedRef.current = false;
      voiceNoteShownRef.current = false;
      umi.transition("THINKING");
    },
    onSentence: (sentence, token) => {
      if (token !== turnTokenRef.current) return;
      micPausedRef.current = true;
      umi.transition("SPEAKING");
      lastSpokenRef.current = sentence;
      pendingSpeaksRef.current += 1;
      tts
        .speak(sentence)
        .catch(() => showVoiceNote())
        .finally(() => {
          if (token === turnTokenRef.current) {
            pendingSpeaksRef.current -= 1;
            maybeFinish();
          }
        });
    },
    onDone: (reply, token) => {
      if (token !== turnTokenRef.current) return;
      streamDoneRef.current = true;
      maybeFinish();
    },
    onError: (message, token) => {
      if (token !== turnTokenRef.current) return;
      pendingSpeaksRef.current = 0;
      micPausedRef.current = false;
      busyRef.current = false;
      turnStartAtRef.current = 0;
      umi.fail(message);
    },
  });

  function toggleVoice() {
    if (!active) {
      void startSession();
      umi.transition("LISTENING");
      return;
    }
    busyRef.current = false;
    void stopSession();
    umi.clearError();
    umi.transition("READY");
  }

  useEffect(() => {
    return () => {
      if (voiceNoteTimerRef.current !== undefined) {
        window.clearTimeout(voiceNoteTimerRef.current);
      }
    };
  }, []);

  const sessionNote = voiceNote ?? error;
  const liveHint =
    active && !sessionNote ? (partial.trim() ? partial : "listening…") : null;

  // Show greeting text when in GREETING state
  const showGreeting = umi.state === "GREETING" && greetingText;

  return (
    <div className="relative flex h-dvh w-full flex-col overflow-hidden bg-holo-bg">
      <HolographicScene state={umi.state} />

      <div className="relative z-10 flex h-full flex-col">
        <StatusIndicator />

        <div className="flex flex-1 flex-col items-center justify-start overflow-y-auto px-6">
          <UmiCore state={umi.state} />

          {showGreeting && (
            <div className="entrance-fade mb-4 text-center text-holo-text/90 text-base font-mono tracking-wide">
              {greetingText}
            </div>
          )}

          {umi.endGreeting && showGreeting && (
            <button
              onClick={() => {
                setGreetingText(null);
                umi.endGreeting();
              }}
              className="entrance-fade mb-4 text-sm text-holo-muted hover:text-holo-text font-mono"
            >
              Dismiss
            </button>
          )}
          {showChat && (
            <Conversation messages={chat.messages} thinking={thinking} canSpeak={false} />
          )}

          {showMemories && (
            <div className="mb-4 flex w-full justify-center">
              <MemoriesPanel />
            </div>
          )}

          {showTasks && (
            <div className="mb-4 flex w-full justify-center">
              <TasksPanel />
            </div>
          )}

          {showGmail && (
            <div className="mb-4 flex w-full justify-center">
              <GmailPanel />
            </div>
          )}
        </div>

        <div className="relative flex flex-col items-center">
          <div className="flex h-6 items-center justify-center px-6">
            {(sessionNote || liveHint) && (
              <p
                className={`entrance-fade max-w-full truncate text-center font-mono text-[11px] tracking-wide ${
                  error ? "text-holo-magenta" : "text-holo-muted"
                }`}
              >
                {sessionNote ?? liveHint}
              </p>
            )}
          </div>
          <div className="flex items-center justify-center px-6 pb-7">
            <div className="flex w-full max-w-2xl items-center gap-2.5 rounded-full border border-holo-border bg-holo-panel/80 px-2.5 py-2 shadow-[0_10px_36px_rgba(0,0,0,0.45)] backdrop-blur-xl">
              <button
                type="button"
                aria-label="Toggle chat"
                title={showChat ? "Hide chat" : "Show chat"}
                onClick={() => setShowChat((v) => !v)}
                className={`grid h-9 w-9 shrink-0 place-items-center rounded-full border transition-colors ${
                  showChat
                    ? "border-holo-border-strong text-holo-magenta"
                    : "border-holo-border text-holo-muted hover:text-holo-magenta"
                }`}
              >
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6">
                  {showChat ? (
                    <>
                      <path d="M7 9l10 6" strokeLinecap="round" />
                      <path d="M4 13.5a8.5 8.5 0 0 0 16 0" strokeLinecap="round" />
                      <path d="M12 13.5V5M12 5l-2.5 2.5M12 5l2.5 2.5" strokeLinecap="round" strokeLinejoin="round" />
                    </>
                  ) : (
                    <>
                      <path d="M21 11.5a7.5 7.5 0 0 1-12 6l-5 1.5 1.5-5A7.5 7.5 0 1 1 21 11.5z" strokeLinecap="round" strokeLinejoin="round" />
                    </>
                  )}
                </svg>
              </button>

              <button
                type="button"
                aria-label="Toggle memories"
                title="Memories"
                onClick={() => setShowMemories((v) => !v)}
                className={`grid h-9 w-9 shrink-0 place-items-center rounded-full border transition-colors ${
                  showMemories
                    ? "border-holo-border-strong text-holo-magenta"
                    : "border-holo-border text-holo-muted hover:text-holo-magenta"
                }`}
              >
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6">
                  <path d="M12 3l8 3-8 3-8-3 8-3z" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M4 9.5l8 3 8-3M4 14l8 3 8-3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              <button
                type="button"
                aria-label="Toggle tasks"
                title="Tasks"
                onClick={() => setShowTasks((v) => !v)}
                className={`grid h-9 w-9 shrink-0 place-items-center rounded-full border transition-colors ${
                  showTasks
                    ? "border-holo-border-strong text-holo-magenta"
                    : "border-holo-border text-holo-muted hover:text-holo-magenta"
                }`}
              >
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6">
                  {showTasks ? (
                    <>
                      <path d="M4 12.5l5 5L20 6.5" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M6 19l12 0M6 5l12 0" strokeLinecap="round" />
                    </>
                  ) : (
                    <>
                      <path d="M4 7c0-1.1.9-2 2-2h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7z" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M8 9l2.5 2.5L15 7" strokeLinecap="round" strokeLinejoin="round" />
                    </>
                  )}
                </svg>
              </button>

              <button
                type="button"
                aria-label="Toggle Gmail"
                title="Gmail"
                onClick={() => setShowGmail((v) => !v)}
                className={`grid h-9 w-9 shrink-0 place-items-center rounded-full border transition-colors ${
                  showGmail
                    ? "border-holo-border-strong text-holo-magenta"
                    : "border-holo-border text-holo-muted hover:text-holo-magenta"
                }`}
              >
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6">
                  <path d="M4 6.5h16v11H4z" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M4 7l8 6 8-6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              <span className="h-5 w-px bg-holo-border" />

              <VoiceControl active={active} mode={mode} onToggle={toggleVoice} />
              <TextInput onSend={startTurn} busy={thinking} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function UmiInterface() {
  return (
    <UmiProvider>
      <UmiExperience />
    </UmiProvider>
  );
}