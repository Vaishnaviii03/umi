"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "../hooks/useChat";
import Message from "./Message";

type ConversationProps = {
  messages: ChatMessage[];
  thinking: boolean;
  canSpeak: boolean;
};

/**
 * Elegant conversation surface. Presented as a translucent panel that appears
 * when there is something to say, never dominating the core presence.
 */
export default function Conversation({ messages, thinking, canSpeak }: ConversationProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, thinking]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex w-full max-w-3xl items-center justify-center px-6">
      {isEmpty && !thinking ? (
        <p className="entrance-fade select-none text-center font-mono text-xs tracking-[0.3em] text-holo-dim">
          {canSpeak
            ? "AWAITING YOUR VOICE"
            : "READY · SAY SOMETHING"}
        </p>
      ) : (
        <div
          ref={scrollRef}
          role="log"
          aria-live="polite"
          className="chat-surface entrance flex max-h-[38vh] w-full flex-col gap-4 overflow-y-auto px-5 py-4"
        >
          {messages.map((m, i) => (
            <Message key={m.id} message={m} isLast={i === messages.length - 1} />
          ))}

          {thinking && (
            <div className="entrance-fade flex items-center gap-2.5 self-start pl-1">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-holo-purple shadow-[0_0_10px_currentColor]" />
              <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-holo-muted">
                Composing
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}