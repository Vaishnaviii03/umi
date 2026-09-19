"use client";

import { useEffect, useMemo, useState } from "react";
import { formatDueLabel, isOverdue, toIsoInput, type Task } from "./lib/tasks";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type Filter = "pending" | "done" | "all";

export default function TasksPanel() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [newTitle, setNewTitle] = useState("");
  const [newDue, setNewDue] = useState("");
  const [filter, setFilter] = useState<Filter>("pending");
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  const load = async () => {
    setError(null);
    try {
      const res = await fetch(`${BACKEND_URL}/tasks`);
      if (res.status === 503) {
        setUnavailable(true);
        setTasks([]);
        return;
      }
      if (!res.ok) throw new Error("Couldn't load tasks.");
      setTasks((await res.json()) as Task[]);
      setUnavailable(false);
    } catch {
      setError("Couldn't load tasks.");
    }
  };

  useEffect(() => {
    const timeout = window.setTimeout(load, 0);
    return () => window.clearTimeout(timeout);
  }, []);

  async function addTask() {
    const title = newTitle.trim();
    if (!title) return;
    setError(null);
    const due_at = toIsoInput(newDue);
    try {
      const res = await fetch(`${BACKEND_URL}/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, due_at }),
      });
      if (res.status === 503) {
        setUnavailable(true);
        return;
      }
      if (!res.ok) throw new Error("Couldn't save task.");
      const created = (await res.json()) as Task;
      setTasks((prev) => [created, ...prev]);
      setNewTitle("");
      setNewDue("");
    } catch {
      setError("Couldn't save task.");
    }
  }

  async function toggle(task: Task) {
    setError(null);
    try {
      const res = await fetch(`${BACKEND_URL}/tasks/${task.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: task.status === "done" ? "pending" : "done" }),
      });
      if (res.status === 503) {
        setUnavailable(true);
        return;
      }
      if (!res.ok) throw new Error("Couldn't update task.");
      const updated = (await res.json()) as Task;
      setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
    } catch {
      setError("Couldn't update task.");
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      const res = await fetch(`${BACKEND_URL}/tasks/${id}`, { method: "DELETE" });
      if (res.status === 503) {
        setUnavailable(true);
        return;
      }
      if (!res.ok) throw new Error("Couldn't delete task.");
      setTasks((prev) => prev.filter((t) => t.id !== id));
    } catch {
      setError("Couldn't delete task.");
    }
  }

  const visible = useMemo(
    () =>
      tasks.filter((t) => {
        if (filter === "all") return true;
        return t.status === filter;
      }),
    [tasks, filter],
  );
  const pendingCount = tasks.filter((t) => t.status === "pending").length;

  const filterTab = (key: Filter, label: string) => (
    <button
      onClick={() => setFilter(key)}
      className={`rounded-full px-3 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors ${
        filter === key
          ? "bg-holo-magenta/15 text-holo-magenta"
          : "text-holo-muted hover:text-holo-soft"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="chat-surface entrance flex w-full max-w-lg flex-col gap-3 p-4">
      {unavailable ? (
        <p className="text-sm text-holo-soft">
          Tasks aren&apos;t available yet — the database isn&apos;t configured.
        </p>
      ) : (
        <>
          <div className="flex items-baseline justify-between">
            <h2 className="font-mono text-[11px] uppercase tracking-[0.3em] text-holo-muted">
              Tasks
            </h2>
            <span className="font-mono text-[10px] text-holo-dim">
              {pendingCount} pending
            </span>
          </div>
          <div className="flex gap-2">
            <input
              className="holo-input flex-1 rounded-full px-4 py-2 text-sm outline-none placeholder:text-holo-dim"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") addTask();
              }}
              placeholder="Add a task Umi should remember…"
            />
            <input
              aria-label="Due date"
              type="date"
              value={newDue}
              onChange={(e) => setNewDue(e.target.value)}
              className="holo-input shrink-0 rounded-full px-3 py-2 text-sm outline-none text-holo-soft"
            />
            <button
              onClick={addTask}
              className="shrink-0 rounded-full border border-holo-border-strong bg-holo-magenta/10 px-4 py-2 text-sm font-medium text-holo-magenta transition-colors hover:bg-holo-magenta/20"
            >
              Add
            </button>
          </div>
          <div className="flex gap-1">
            {filterTab("pending", "Pending")}
            {filterTab("all", "All")}
            {filterTab("done", "Done")}
          </div>
          {visible.length === 0 && (
            <p className="text-sm text-holo-dim">No tasks here yet.</p>
          )}
          <ul className="flex max-h-44 flex-col gap-2 overflow-y-auto">
            {visible.map((task) => {
              const overdue = task.status === "pending" && isOverdue(task.due_at);
              const dueLabel = formatDueLabel(task.due_at);
              return (
                <li
                  key={task.id}
                  className="flex items-center gap-3 rounded-xl border border-holo-border bg-white/[0.03] px-3 py-2"
                >
                  <button
                    onClick={() => toggle(task)}
                    aria-label={task.status === "done" ? "Mark not done" : "Mark done"}
                    className={`grid h-4 w-4 shrink-0 place-items-center rounded-full border transition-colors ${
                      task.status === "done"
                        ? "border-holo-magenta bg-holo-magenta text-black"
                        : "border-holo-border-strong text-transparent hover:text-holo-muted"
                    }`}
                  >
                    <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="3">
                      <path d="M4 12.5l5 5L20 6.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                  <span
                    className={`flex-1 text-sm leading-relaxed ${
                      task.status === "done"
                        ? "text-holo-dim line-through"
                        : "text-holo-soft"
                    }`}
                  >
                    {task.title}
                  </span>
                  {dueLabel && (
                    <span
                      className={`shrink-0 font-mono text-[10px] ${
                        overdue ? "text-holo-danger" : "text-holo-muted"
                      }`}
                    >
                      {dueLabel}
                      {overdue ? " · overdue" : ""}
                    </span>
                  )}
                  <button
                    onClick={() => remove(task.id)}
                    aria-label="Delete task"
                    className="shrink-0 text-sm text-holo-dim transition-colors hover:text-holo-danger"
                  >
                    ✕
                  </button>
                </li>
              );
            })}
          </ul>
          {error && <p className="text-sm text-holo-danger">{error}</p>}
        </>
      )}
    </div>
  );
}