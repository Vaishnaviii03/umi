/** Pure task/date helpers for the TasksPanel (no DOM, node-testable). */

export type Task = {
  id: string;
  title: string;
  status: "pending" | "done";
  due_at: string | null;
  created_at: string;
  updated_at: string;
};

const DAY_MS = 86_400_000;

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** Friendly due label: "Today", "Tomorrow", "Yesterday", else "Sep 11". */
export function formatDueLabel(iso: string | null, now: Date = new Date()): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;

  const dayDiff = Math.round((startOfDay(d) - startOfDay(now)) / DAY_MS);
  let label: string;
  if (dayDiff === 0) label = "Today";
  else if (dayDiff === 1) label = "Tomorrow";
  else if (dayDiff === -1) label = "Yesterday";
  else label = d.toLocaleDateString(undefined, { month: "short", day: "numeric" });

  if (/T\d{2}:\d{2}/.test(iso)) {
    label += ` · ${d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
  }
  return label;
}

/** True when the task's due moment is in the past. */
export function isOverdue(iso: string | null, now: Date = new Date()): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  return !Number.isNaN(d.getTime()) && d.getTime() < now.getTime();
}

/**
 * Normalize a due-date input ("2026-09-11" or an ISO datetime) to a value the
 * backend accepts, or null when blank/invalid. `input type="date"` produces
 * "YYYY-MM-DD", which the backend parses as midnight local time.
 */
export function toIsoInput(value: string): string | null {
  const raw = (value || "").trim();
  if (!raw) return null;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return null;
  return raw;
}