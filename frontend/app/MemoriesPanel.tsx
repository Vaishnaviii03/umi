"use client";

import { useCallback, useEffect, useState } from "react";

type Memory = { id: string; content: string; created_at: string; updated_at: string };

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export default function MemoriesPanel() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [newMemory, setNewMemory] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetch(`${BACKEND_URL}/memories`);
      if (res.status === 503) {
        setUnavailable(true);
        setMemories([]);
        return;
      }
      if (!res.ok) throw new Error("Couldn't load memories.");
      setMemories((await res.json()) as Memory[]);
      setUnavailable(false);
    } catch {
      setError("Couldn't load memories.");
    }
  }, []);

  useEffect(() => {
    const timeout = window.setTimeout(load, 0);
    return () => window.clearTimeout(timeout);
  }, [load]);

  async function addMemory() {
    const content = newMemory.trim();
    if (!content) return;
    setError(null);
    try {
      const res = await fetch(`${BACKEND_URL}/memories`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (res.status === 503) {
        setUnavailable(true);
        return;
      }
      if (!res.ok) throw new Error("Couldn't save memory.");
      const created = (await res.json()) as Memory;
      setMemories((prev) => [created, ...prev]);
      setNewMemory("");
    } catch {
      setError("Couldn't save memory.");
    }
  }

  async function deleteMemory(id: string) {
    setError(null);
    try {
      const res = await fetch(`${BACKEND_URL}/memories/${id}`, { method: "DELETE" });
      if (res.status === 503) {
        setUnavailable(true);
        return;
      }
      if (!res.ok) throw new Error("Couldn't delete memory.");
      setMemories((prev) => prev.filter((m) => m.id !== id));
    } catch {
      setError("Couldn't delete memory.");
    }
  }

  return (
    <div className="chat-surface entrance flex w-full max-w-lg flex-col gap-3 p-4">
      {unavailable ? (
        <p className="text-sm text-holo-soft">
          Memory isn&apos;t available yet — the database isn&apos;t configured.
        </p>
      ) : (
        <>
          <div className="flex items-baseline justify-between">
            <h2 className="font-mono text-[11px] uppercase tracking-[0.3em] text-holo-muted">
              Memories
            </h2>
            <span className="font-mono text-[10px] text-holo-dim">persistent</span>
          </div>
          <div className="flex gap-2">
            <input
              className="holo-input flex-1 rounded-full px-4 py-2 text-sm outline-none placeholder:text-holo-dim"
              value={newMemory}
              onChange={(e) => setNewMemory(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") addMemory();
              }}
              placeholder="Add a memory Umi should keep…"
            />
            <button
              onClick={addMemory}
              className="shrink-0 rounded-full border border-holo-border-strong bg-holo-magenta/10 px-4 py-2 text-sm font-medium text-holo-magenta transition-colors hover:bg-holo-magenta/20"
            >
              Save
            </button>
          </div>
          {memories.length === 0 && (
            <p className="text-sm text-holo-dim">No memories yet.</p>
          )}
          <ul className="flex max-h-44 flex-col gap-2 overflow-y-auto">
            {memories.map((m) => (
              <li
                key={m.id}
                className="flex items-start justify-between gap-3 rounded-xl border border-holo-border bg-white/[0.03] px-3 py-2"
              >
                <span className="flex-1 text-sm leading-relaxed text-holo-soft">{m.content}</span>
                <button
                  onClick={() => deleteMemory(m.id)}
                  aria-label="Delete memory"
                  className="text-sm text-holo-dim transition-colors hover:text-holo-danger"
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
          {error && <p className="text-sm text-holo-danger">{error}</p>}
        </>
      )}
    </div>
  );
}