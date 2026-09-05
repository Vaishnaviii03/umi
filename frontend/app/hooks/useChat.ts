"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
  send: (text: string, turnToken: number) => Promise<void>;
  reset: () => void;
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
  const conversationIdRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
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
  }, []);

  const sendLegacy = useCallback(
    async (text: string, token: number) => {
      const res = await fetch(`${BACKEND_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          conversation_id: conversationIdRef.current,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? "Umi couldn't respond right now.");
      }
      const data = (await res.json()) as {
        reply: string;
        conversation_id: string | null;
      };
      if (data.conversation_id) conversationIdRef.current = data.conversation_id;
      if (data.reply.trim()) onSentence(data.reply, token);
      onDone(data.reply, token);
    },
    [onSentence, onDone],
  );

  const send = useCallback(
    async (text: string, token: number) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      setMessages((prev) => [...prev, { id: newId(), role: "user", text: trimmed }]);
      onThinking(token);

      try {
        const response = await fetch(`${BACKEND_URL}/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: trimmed,
            conversation_id: conversationIdRef.current,
          }),
        });

        if (response.status === 404 || response.status === 405) {
          // Older backend without SSE — degrade to the non-streaming contract.
          await sendLegacy(trimmed, token);
          return;
        }
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(body?.detail ?? "Umi couldn't respond right now.");
        }
        if (!response.body || !response.body.getReader) {
          await sendLegacy(trimmed, token);
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
                  if (event.conversation_id) conversationIdRef.current = event.conversation_id;
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
        const message = err instanceof Error ? err.message : "Something went wrong.";
        onError(message, token);
      }
    },
    [onThinking, onSentence, onDone, onError, sendLegacy],
  );

  const reset = useCallback(() => {
    conversationIdRef.current = null;
    setMessages([]);
  }, []);

  return { messages, send, reset };
}