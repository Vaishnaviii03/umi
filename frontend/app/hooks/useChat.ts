"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { chatRequestBody, parseSessionResponse, readStoredConversationId, storeConversationId, type SessionInfo } from "../lib/chat";
import { popCompletedSentences } from "../lib/speech";

export type ChatRole = "user" | "umi";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
};

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type ChatApi = {
  messages: ChatMessage[];
  /** Resumed session state: the conversation the next turn will join. */
  session: SessionInfo;
  send: (text: string, turnToken: number, voice?: boolean) => Promise<void>;
  /** Open a proactive (idle) conversation — no user message, spoken reply. */
  sendProactive: (turnToken: number) => Promise<void>;
  /** Abort the in-flight request for the current turn (barge-in). */
  cancel: () => void;
  reset: () => void;
  appendMessage: (role: ChatRole, text: string) => void;
};

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * The one place the UI talks to the Umi backend.
 *
 * Streams the reply from POST /chat/stream (SSE): real model text is surfaced
 * incrementally and completed sentences are handed to `onSentence` as soon as
 * they are generated so TTS can start before the reply finishes. Falls back to
 * the non-streaming POST /chat when the streaming endpoint isn't available.
 * Every callback carries a turn token so the orchestrator can ignore stale
 * events from an interrupted turn.
 */
export function useChat(
  dependencies: {
    onThinking: (token: number) => void;
    onSentence: (sentence: string, token: number) => void;
    onDone: (reply: string, token: number) => void;
    onError: (message: string, token: number) => void;
  },
): ChatApi {
  const { onThinking, onSentence, onDone, onError } = dependencies;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [session, setSession] = useState<SessionInfo>({
    conversationId: null,
    resumed: false,
    greetingOwed: false,
    greetingNew: false,
    idle: null,
  });
  const conversationIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const isAbortError = useCallback((err: unknown): boolean => {
    return err instanceof Error && err.name === "AbortError";
  }, []);

  const storage = typeof window !== "undefined" ? window.sessionStorage : null;

  useEffect(() => {
    let cancelled = false;
    // Restore a previously persisted conversation so the first turn after a
    // reload is never sent as conversation_id: null (greeting-once depends on
    // this, and continuity does too).
    const stored = readStoredConversationId(storage);
    if (stored) conversationIdRef.current = stored;

    fetch(`${BACKEND_URL}/session`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (cancelled || !data) return;
        const parsed = parseSessionResponse(data);
        if (parsed.conversationId) {
          conversationIdRef.current = parsed.conversationId;
          storeConversationId(storage, parsed.conversationId);
        }
        setSession(parsed);
      })
      .catch(() => {
        // Database unavailable — keep any stored id; chat still works.
      });

    fetch(`${BACKEND_URL}/conversations/active/messages`)
      .then((res) => {
        if (!res.ok) return null;
        return res.json();
      })
      .then((data) => {
        if (cancelled || !Array.isArray(data)) return;
        const hydrated = data
          .map((m: { role: string; content: string }) => ({
            id: newId(),
            role: m.role === "assistant" ? ("umi" as const) : ("user" as const),
            text: m.content,
          }))
          .filter((m: ChatMessage) => m.text.trim().length > 0);
        setMessages(hydrated);
      })
      .catch(() => {
        // Database unavailable — start fresh; chat still works.
      });
    return () => {
      cancelled = true;
    };
  }, [storage]);

  const sendLegacy = useCallback(
    async (text: string, token: number, voice: boolean, signal?: AbortSignal, proactive = false) => {
      const res = await fetch(`${BACKEND_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(chatRequestBody(text, conversationIdRef.current, voice, proactive)),
        signal,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? "Umi couldn't respond right now.");
      }
      const data = (await res.json()) as {
        reply: string;
        conversation_id: string | null;
      };
      if (data.conversation_id) {
        conversationIdRef.current = data.conversation_id;
        storeConversationId(storage, data.conversation_id);
      }
      if (!data.reply.trim()) return;
    onSentence(data.reply, token);
    onDone(data.reply, token);
  },
  [onSentence, onDone, storage],
);

  const send = useCallback(
    async (text: string, token: number, voice?: boolean, proactive = false) => {
      const trimmed = text.trim();
      if (!proactive && !trimmed) return;

      if (!proactive) {
        setMessages((prev) => [...prev, { id: newId(), role: "user", text: trimmed }]);
      }
      onThinking(token);

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const signal = controller.signal;

      try {
        const response = await fetch(`${BACKEND_URL}/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            chatRequestBody(trimmed, conversationIdRef.current, voice ?? false, proactive),
          ),
          signal,
        });

        if (response.status === 404 || response.status === 405) {
          // Older backend without SSE — degrade to the non-streaming contract.
          await sendLegacy(trimmed, token, voice ?? false, signal, proactive);
          return;
        }
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(body?.detail ?? "Umi couldn't respond right now.");
        }
        if (!response.body || !response.body.getReader) {
          await sendLegacy(trimmed, token, voice ?? false, signal, proactive);
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let sseBuffer = "";
        let sentenceBuffer = "";
        let reply = "";
        let umiId: string | null = null;

        const emitSentence = (sentence: string) => {
          if (sentence.trim()) onSentence(sentence.trim(), token);
        };

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            sseBuffer += decoder.decode(value, { stream: true });

            let frameEnd = sseBuffer.indexOf("\n\n");
            while (frameEnd !== -1) {
              const frame = sseBuffer.slice(0, frameEnd);
              sseBuffer = sseBuffer.slice(frameEnd + 2);
              const dataLine = frame.split("\n").find((line) => line.startsWith("data:"));
              if (dataLine) {
                let event: {
                  text?: string;
                  done?: boolean;
                  reply?: string;
                  conversation_id?: string | null;
                  error?: string;
                };
                try {
                  event = JSON.parse(dataLine.slice(5).trim());
                } catch {
                  frameEnd = sseBuffer.indexOf("\n\n");
                  continue;
                }

                if (event.text) {
                  reply += event.text;
                  if (umiId === null) {
                    umiId = newId();
                    setMessages((prev) => [...prev, { id: umiId!, role: "umi", text: "" }]);
                  }
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === umiId && m.text !== reply ? { ...m, text: reply } : m,
                    ),
                  );
                  sentenceBuffer += event.text;
                  const { complete, remainder } = popCompletedSentences(sentenceBuffer);
                  for (const sentence of complete) emitSentence(sentence);
                  sentenceBuffer = remainder;
                } else if (event.done) {
                  if (event.reply != null) {
                    reply = event.reply;
                  }
                  if (event.conversation_id) {
                    conversationIdRef.current = event.conversation_id;
                    storeConversationId(storage, event.conversation_id);
                  }
                  if (sentenceBuffer.trim()) emitSentence(sentenceBuffer.trim());
                  if (umiId === null) {
                    umiId = newId();
                    setMessages((prev) => [...prev, { id: umiId!, role: "umi", text: reply }]);
                  } else {
                    setMessages((prev) =>
                      prev.map((m) => (m.id === umiId ? { ...m, text: reply } : m)),
                    );
                  }
                  onDone(reply, token);
                  return;
                } else if (event.error) {
                  throw new Error(event.error ?? "Umi couldn't respond right now.");
                }
              }
              frameEnd = sseBuffer.indexOf("\n\n");
            }
          }
          // Stream ended without a final event.
          throw new Error("Umi couldn't respond right now.");
        } finally {
          reader.releaseLock?.();
        }
      } catch (err) {
        if (isAbortError(err)) return;
        const message = err instanceof Error ? err.message : "Something went wrong.";
        onError(message, token);
      }
    },
    [onThinking, onSentence, onDone, onError, sendLegacy, isAbortError, storage],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const sendProactive = useCallback(
    async (token: number) => {
      // No user message, spoken opener — the backend enforces the idle policy.
      await send("", token, true, true);
    },
    [send],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    conversationIdRef.current = null;
    storeConversationId(storage, null);
    setSession({ conversationId: null, resumed: false, greetingOwed: false, greetingNew: false, idle: null });
    setMessages([]);
  }, [storage]);

  const appendMessage = useCallback((role: ChatRole, text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setMessages((prev) => [...prev, { id: newId(), role, text: trimmed }]);
  }, []);

  return { messages, session, send, sendProactive, cancel, reset, appendMessage };
}