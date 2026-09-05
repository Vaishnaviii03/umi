"use client";

import type { ChatMessage } from "../hooks/useChat";

type MessageProps = {
  message: ChatMessage;
  isLast: boolean;
};

/**
 * A single exchange. User lines sit right-aligned in a soft glass chip; Umi
 * replies sit left with a faint tag. No heavy cards, no chrome.
 */
export default function Message({ message, isLast }: MessageProps) {
  const isUser = message.role === "user";

  return (
    <div className={`entrance flex w-full ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`flex max-w-[85%] flex-col gap-1 ${
          isUser ? "items-end" : "items-start"
        }`}
      >
        {!isUser && (
          <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-holo-muted">
            Umi
          </span>
        )}
        <span
          className={`whitespace-pre-wrap text-[13.5px] leading-relaxed ${
            isUser
              ? "rounded-2xl rounded-br-sm border border-holo-border bg-white/[0.05] px-3.5 py-2 text-holo-soft"
              : "text-holo-ink"
          }`}
        >
          {message.text}
        </span>
        {isLast && !isUser && (
          <span className="mt-0.5 h-px w-10 bg-gradient-to-r from-holo-magenta/70 to-transparent" />
        )}
      </div>
    </div>
  );
}