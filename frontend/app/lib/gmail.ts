/** Pure Gmail helpers + the REST client wrapper (no React, node-testable). */

export type GmailEmail = {
  id: string;
  subject: string;
  from_header?: string | null;
  from_name?: string;
  from_email?: string;
  date?: string | null;
  snippet?: string;
  unread?: boolean;
  importance_level?: string;
  importance_score?: number;
  thread_length?: number;
  body?: string;
  labels?: string[];
};

export type GmailDraft = { id: string; to?: string; subject?: string; snippet?: string };

export type GmailStatus = { connected: boolean; email?: string | null };

/** Six Google capabilities Umi now speaks over the one OAuth connection. */
export const GOOGLE_SERVICES = ["Gmail", "Calendar", "Drive", "Sheets", "Docs", "YouTube"] as const;
export type GoogleService = (typeof GOOGLE_SERVICES)[number];

export type GoogleStatus = {
  connected: boolean;
  email?: string | null;
  granted_scopes: string[];
  required_scopes: string[];
  needs_reauthorization: boolean;
};

/** Short scope keys per service (match against the full URL scopes). */
const SERVICE_SCOPE_KEYS: Record<GoogleService, string[]> = {
  Gmail: ["gmail.modify"],
  Calendar: ["calendar.readonly", "calendar.events"],
  Drive: ["drive"],
  Sheets: ["spreadsheets"],
  Docs: ["documents"],
  YouTube: ["youtube"],
};

/** Which of the six services the stored token actually covers. */
export function servicesCovered(status: GoogleStatus | null | undefined): GoogleService[] {
  if (!status || !status.connected) return [];
  return GOOGLE_SERVICES.filter((service) =>
    SERVICE_SCOPE_KEYS[service].some((key) => status.granted_scopes.some((g) => g.includes(key))),
  );
}

/** Message for the reconnect call-to-action when the token predates new scopes. */
export function reauthorizeMessage(status: GoogleStatus | null | undefined): string | null {
  if (!status || !status.connected || !status.needs_reauthorization) return null;
  const missing = GOOGLE_SERVICES.filter(
    (service) =>
      !status.granted_scopes.some((g) => SERVICE_SCOPE_KEYS[service].some((key) => g.includes(key))),
  );
  if (missing.length === 0) return null;
  return `Reconnect to enable ${missing.join(", ")}`;
}

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, init);
  if (res.status === 503) throw new GmailUnavailable();
  if (res.status === 401) throw new GmailNotConnected();
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? "Gmail request failed.");
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export class GmailNotConnected extends Error {}
export class GmailUnavailable extends Error {}

export function api() {
  return {
    status: () => request<GmailStatus>("/gmail/status"),
    googleStatus: () => request<GoogleStatus>("/google/status"),
    authUrl: () => request<{ authorization_url: string }>("/gmail/auth"),
    disconnect: () => request<GmailStatus>("/gmail/disconnect", { method: "POST" }),
    listEmails: (unreadOnly = false, limit = 25) =>
      request<GmailEmail[]>(`/gmail/emails?unread_only=${unreadOnly}&limit=${limit}`),
    getEmail: (id: string) => request<GmailEmail>(`/gmail/emails/${id}`),
    search: (q: string, limit = 25) =>
      request<GmailEmail[]>(`/gmail/search?q=${encodeURIComponent(q)}&limit=${limit}`),
    drafts: () => request<GmailDraft[]>("/gmail/drafts"),
    createDraft: (d: { to: string; subject: string; body: string }) =>
      request<GmailDraft>("/gmail/drafts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(d),
      }),
    sendDraft: (draftId: string) =>
      request<{ message_id: string }>("/gmail/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draft_id: draftId }),
      }),
    summarize: (unreadOnly = true) =>
      request<{ brief: string }>("/gmail/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ unread_only: unreadOnly }),
      }),
  };
}

/** Friendly from label: prefers the name, falls back to the bare address. */
export function fromLabel(email: GmailEmail): string {
  if (email.from_name) return email.from_name;
  const addr = email.from_email || email.from_header || "";
  return addr.replace(/^.*<([^>]+)>.*$/, "$1") || "Unknown";
}

/** Map the OAuth callback's ?gmail=error&error=<kind> to a user-facing message. */
export function connectErrorMessage(search: string): string | null {
  const p = new URLSearchParams(search);
  if (p.get("gmail") !== "error") return null;
  const kind = p.get("error") ?? "";
  if (kind === "denied" || kind === "access_denied") return "Google sign-in was cancelled.";
  if (kind === "auth-failed") return "Google sign-in failed on Umi's side. Please try again.";
  return "Google sign-in failed.";
}

/** Short relative time: "now", "5m", "3h", "2d", else a date. */
export function timeAgo(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const diff = now.getTime() - d.getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}