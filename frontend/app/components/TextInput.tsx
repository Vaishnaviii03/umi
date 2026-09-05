"use client";

import { useState, type FormEvent } from "react";

type TextInputProps = {
  onSend: (text: string) => void;
  busy: boolean;
  disabled?: boolean;
};

/**
 * Minimal command line. Enter to send; the send glyph is gentle, not a big
 * button. Merged into the same floating dock as the voice control.
 */
export default function TextInput({ onSend, busy, disabled = false }: TextInputProps) {
  const [value, setValue] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    const text = value.trim();
    if (!text || busy || disabled) return;
    onSend(text);
    setValue("");
  }

  return (
    <form
      className="flex flex-1 items-center gap-2 rounded-full py-1.5 pl-3 pr-1.5"
      onSubmit={submit}
    >
      <input
        aria-label="Message Umi"
        className="w-full bg-transparent text-sm text-holo-ink outline-none"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Message Umi…"
        disabled={disabled}
        spellCheck={false}
      />
      <button
        type="submit"
        aria-label="Send message"
        disabled={busy || disabled || !value.trim()}
        className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-holo-muted transition-colors hover:bg-white/5 hover:text-holo-magenta disabled:opacity-30"
      >
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M12 19V5M5 12l7-7 7 7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </form>
  );
}