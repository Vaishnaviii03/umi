"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  GmailNotConnected,
  GmailUnavailable,
  api,
  connectErrorMessage,
  fromLabel,
  reauthorizeMessage,
  servicesCovered,
  timeAgo,
  GOOGLE_SERVICES,
  type GmailDraft,
  type GmailEmail,
  type GoogleStatus,
} from "./lib/gmail";
import {
  fetchIntegrationsStatus,
  integrationActive,
  integrationLabel,
  integrationStatusLabel,
  INTEGRATION_PLATFORMS,
  type IntegrationsStatus,
} from "./lib/integrations";

const SEND_CONFIRM_TEXT = "I confirm I want to send this draft to the recipient.";

type Mode = "inbox" | "read" | "drafts";

export default function GmailPanel() {
  const gmail = useMemo(() => api(), []);
  const [connected, setConnected] = useState(false);
  const [account, setAccount] = useState<string | null>(null);
  const [googleStatus, setGoogleStatus] = useState<GoogleStatus | null>(null);
  const [integrations, setIntegrations] = useState<IntegrationsStatus | null>(null);
  const [emails, setEmails] = useState<GmailEmail[]>([]);
  const [select, setSelect] = useState<GmailEmail | null>(null);
  const [drafts, setDrafts] = useState<GmailDraft[]>([]);
  const [brief, setBrief] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("inbox");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [draftTo, setDraftTo] = useState("");
  const [draftSubject, setDraftSubject] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [sending, setSending] = useState<string | null>(null);

  const refreshStatus = useCallback(async () => {
    try {
      const [gs, its] = await Promise.allSettled([
        gmail.googleStatus(),
        fetchIntegrationsStatus(),
      ]);
      const s = await gmail.status();
      setConnected(s.connected);
      setAccount(s.email ?? null);
      setGoogleStatus(gs.status === "fulfilled" ? gs.value : null);
      setIntegrations(its.status === "fulfilled" ? its.value : null);
    } catch (err) {
      if (err instanceof GmailUnavailable) setUnavailable(true);
    }
  }, [gmail]);

  useEffect(() => {
    const timeout = window.setTimeout(() => void refreshStatus(), 0);
    return () => window.clearTimeout(timeout);
  }, [refreshStatus]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauthError = connectErrorMessage(window.location.search);
    if (oauthError) {
      const timeout = window.setTimeout(() => {
        params.delete("gmail");
        params.delete("error");
        const qs = params.toString();
        window.history.replaceState({}, "", window.location.pathname + (qs ? `?${qs}` : ""));
        setError(oauthError);
      }, 0);
      return () => window.clearTimeout(timeout);
    }
    if (params.get("gmail") === "connected") {
      const timeout = window.setTimeout(() => {
        params.delete("gmail");
        params.delete("error");
        const qs = params.toString();
        window.history.replaceState({}, "", window.location.pathname + (qs ? `?${qs}` : ""));
        void refreshStatus();
      }, 0);
      return () => window.clearTimeout(timeout);
    }
  }, [refreshStatus]);

  async function connect() {
    setError(null);
    try {
      const { authorization_url } = await gmail.authUrl();
      window.location.href = authorization_url;
    } catch (err) {
      if (err instanceof GmailUnavailable) setUnavailable(true);
      else setError("Couldn't start Google sign-in.");
    }
  }

  async function loadInbox() {
    setLoading(true);
    setError(null);
    try {
      setEmails(await gmail.listEmails(true));
    } catch (err) {
      handleErr(err);
    } finally {
      setLoading(false);
    }
  }

  async function runSearch() {
    setLoading(true);
    setError(null);
    try {
      setEmails(query.trim() ? await gmail.search(query) : await gmail.listEmails(true));
    } catch (err) {
      handleErr(err);
    } finally {
      setLoading(false);
    }
  }

  async function openEmail(email: GmailEmail) {
    setLoading(true);
    setError(null);
    try {
      setSelect(await gmail.getEmail(email.id));
      setMode("read");
    } catch (err) {
      handleErr(err);
    } finally {
      setLoading(false);
    }
  }

  async function summarize() {
    setLoading(true);
    setError(null);
    try {
      setBrief((await gmail.summarize(true)).brief);
    } catch (err) {
      handleErr(err);
    } finally {
      setLoading(false);
    }
  }

  async function loadDrafts() {
    setLoading(true);
    setError(null);
    try {
      setDrafts(await gmail.drafts());
      setMode("drafts");
    } catch (err) {
      handleErr(err);
    } finally {
      setLoading(false);
    }
  }

  async function saveDraft() {
    if (!draftTo.trim() || !draftSubject.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await gmail.createDraft({ to: draftTo, subject: draftSubject, body: draftBody });
      setDraftTo("");
      setDraftSubject("");
      setDraftBody("");
      setConfirmText("");
      await loadDrafts();
    } catch (err) {
      handleErr(err);
    } finally {
      setLoading(false);
    }
  }

  async function sendDraft(draft: GmailDraft) {
    if (sending) return;
    setSending(draft.id);
    setError(null);
    try {
      await gmail.sendDraft(draft.id);
      setDrafts((prev) => prev.filter((d) => d.id !== draft.id));
      setConfirmText("");
    } catch (err) {
      handleErr(err);
    } finally {
      setSending(null);
    }
  }

  async function disconnect() {
    try {
      await gmail.disconnect();
      setConnected(false);
      setAccount(null);
      setEmails([]);
      setSelect(null);
      setDrafts([]);
      setBrief(null);
    } catch {
      setError("Couldn't disconnect.");
    }
  }

  function handleErr(err: unknown) {
    if (err instanceof GmailUnavailable) {
      setUnavailable(true);
    } else if (err instanceof GmailNotConnected) {
      setConnected(false);
      setAccount(null);
      setError("No Google account connected.");
    } else {
      setError(err instanceof Error ? err.message : "Gmail request failed.");
    }
  }

  const levelColor = (level?: string) =>
    level === "high" ? "text-holo-danger" : level === "medium" ? "text-holo-amber" : "text-holo-dim";

  if (unavailable) {
    return (
      <div className="chat-surface entrance flex w-full max-w-lg flex-col gap-3 p-4">
        <p className="text-sm text-holo-soft">
          Gmail isn&apos;t available yet — the backend needs Google OAuth credentials
          (see the Gmail setup steps in Phase.md).
        </p>
      </div>
    );
  }

  return (
    <div className="chat-surface entrance flex w-full max-w-lg flex-col gap-3 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.3em] text-holo-muted">
          Gmail
        </h2>
        {connected ? (
          <span className="font-mono text-[10px] text-holo-dim">{account}</span>
        ) : (
          <button
            onClick={connect}
            className="rounded-full border border-holo-border-strong bg-holo-magenta/10 px-3 py-1 text-[11px] font-medium text-holo-magenta hover:bg-holo-magenta/20"
          >
            Connect Google
          </button>
        )}
      </div>

      <div className="flex items-center gap-1.5 flex-wrap">
        {INTEGRATION_PLATFORMS.map((platform) => {
          const state = integrations?.[platform] ?? null;
          const active = integrationActive(state);
          return (
            <span
              key={platform}
              className={`rounded-full px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider ${
                active ? "bg-holo-mint/10 text-holo-mint" : "bg-white/[0.03] text-holo-dim"
              }`}
              title={`${integrationLabel(platform)} — ${integrationStatusLabel(state)}${state?.detail ? ` (${state.detail})` : ""}`}
            >
              {integrationLabel(platform)}
            </span>
          );
        })}
      </div>

      {googleStatus && (
        <>
          <div className="flex items-center gap-1.5 flex-wrap">
            {GOOGLE_SERVICES.map((svc) => {
              const covered = servicesCovered(googleStatus).includes(svc);
              return (
                <span
                  key={svc}
                  className={`rounded-full px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider ${
                    covered ? "bg-holo-mint/10 text-holo-mint" : "bg-white/[0.03] text-holo-dim"
                  }`}
                  title={covered ? `${svc} is enabled` : `${svc} requires reconnection`}
                >
                  {svc}
                </span>
              );
            })}
          </div>

          {reauthorizeMessage(googleStatus) && (
            <div className="flex items-center justify-between gap-3 rounded-xl border border-holo-amber/40 bg-holo-amber/[0.04] px-3 py-2">
              <span className="text-xs text-holo-amber">{reauthorizeMessage(googleStatus)}</span>
              <button
                onClick={connect}
                className="rounded-full border border-holo-amber/40 px-3 py-1 text-[11px] font-medium text-holo-amber hover:bg-holo-amber/10"
              >
                Reconnect
              </button>
            </div>
          )}
        </>
      )}

      {connected && (
        <>
          <div className="flex items-center gap-1.5">
            {(
              [
                ["inbox", "Inbox"],
                ["drafts", "Drafts"],
              ] as [Mode, string][]
            ).map(([key, label]) => (
              <button
                key={key}
                onClick={() => {
                  setMode(key);
                  if (key === "inbox") void loadInbox();
                  if (key === "drafts") void loadDrafts();
                }}
                className={`rounded-full px-3 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors ${
                  mode === key ? "bg-holo-magenta/15 text-holo-magenta" : "text-holo-muted hover:text-holo-soft"
                }`}
              >
                {label}
              </button>
            ))}
            <button
              onClick={() => void summarize()}
              disabled={loading}
              className="ml-auto rounded-full border border-holo-border px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-holo-muted hover:text-holo-soft"
            >
              Summarize inbox
            </button>
            <button
              onClick={disconnect}
              className="rounded-full px-2 py-1 font-mono text-[10px] text-holo-dim hover:text-holo-danger"
            >
              Disconnect
            </button>
          </div>

          {brief && (
            <div className="rounded-xl border border-holo-border bg-white/[0.03] p-3 text-sm leading-relaxed text-holo-soft">
              <div className="mb-1 flex items-baseline justify-between">
                <span className="font-mono text-[10px] uppercase tracking-wider text-holo-muted">Brief</span>
                <button onClick={() => setBrief(null)} className="text-holo-dim hover:text-holo-danger">
                  ✕
                </button>
              </div>
              <p className="whitespace-pre-wrap">{brief}</p>
            </div>
          )}

          {mode === "inbox" && (
            <>
              <div className="flex items-center gap-2">
                <input
                  className="holo-input flex-1 rounded-full px-4 py-2 text-sm outline-none placeholder:text-holo-dim"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !loading && void runSearch()}
                  placeholder="Search Gmail… e.g. from:alice"                />
              </div>

              {select && (
                <div className="rounded-xl border border-holo-border bg-white/[0.03] p-3">
                  <button onClick={() => setSelect(null)} className="mb-2 font-mono text-[10px] text-holo-muted hover:text-holo-soft">
                    ← back
                  </button>
                  <h3 className="text-sm font-semibold text-holo-text">{select.subject}</h3>
                  <p className="mt-1 text-xs text-holo-muted">
                    {fromLabel(select)}{" "}
                    {select.date ? `· ${new Date(select.date).toLocaleString()}` : ""}
                  </p>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-holo-soft">
                    {select.body || "(no body)"}
                  </p>
                </div>
              )}

              <div className="flex items-center justify-end">
                <button
                  onClick={() => void loadInbox()}
                  disabled={loading}
                  className="font-mono text-[10px] uppercase tracking-wider text-holo-muted hover:text-holo-soft"
                >
                  {loading ? "Loading…" : "Refresh"}
                </button>
              </div>

              {emails.length === 0 && !loading && (
                <p className="text-sm text-holo-dim">No emails {query ? "match" : "in the unread inbox"}.</p>
              )}
              <ul className="flex max-h-56 flex-col gap-2 overflow-y-auto">
                {emails.map((e) => (
                  <button
                    key={e.id}
                    onClick={() => void openEmail(e)}
                    className="flex items-start gap-3 rounded-xl border border-holo-border bg-white/[0.03] px-3 py-2 text-left transition-colors hover:bg-white/[0.06]"
                  >
                    <span className={`mt-0.5 shrink-0 font-mono text-[9px] uppercase ${levelColor(e.importance_level)}`}>
                      {e.importance_level ?? "low"}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline justify-between gap-2">
                        <span className={e.unread ? "truncate text-sm font-semibold text-holo-text" : "truncate text-sm text-holo-soft"}>
                          {e.subject || "(no subject)"}
                        </span>
                        <span className="shrink-0 font-mono text-[10px] text-holo-dim">{timeAgo(e.date)}</span>
                      </span>
                      <span className="block truncate text-xs text-holo-muted">
                        {fromLabel(e)} · {e.snippet}
                      </span>
                    </span>
                  </button>
                ))}
              </ul>
            </>
          )}

          {mode === "drafts" && (
            <>
              <div className="rounded-xl border border-holo-border bg-white/[0.03] p-3">
                <p className="mb-2 font-mono text-[10px] uppercase tracking-wider text-holo-muted">
                  New draft
                </p>
                <input
                  className="holo-input mb-2 w-full rounded-lg px-3 py-2 text-sm outline-none placeholder:text-holo-dim"
                  placeholder="To (email)"
                  value={draftTo}
                  onChange={(e) => setDraftTo(e.target.value)}
                />
                <input
                  className="holo-input mb-2 w-full rounded-lg px-3 py-2 text-sm outline-none placeholder:text-holo-dim"
                  placeholder="Subject"
                  value={draftSubject}
                  onChange={(e) => setDraftSubject(e.target.value)}
                />
                <textarea
                  className="holo-input h-24 w-full rounded-lg px-3 py-2 text-sm outline-none placeholder:text-holo-dim"
                  placeholder="Body…"
                  value={draftBody}
                  onChange={(e) => setDraftBody(e.target.value)}
                />
                <div className="mt-2 flex justify-end">
                  <button
                    onClick={() => void saveDraft()}
                    disabled={loading || !draftTo.trim() || !draftSubject.trim()}
                    className="rounded-full border border-holo-border-strong bg-holo-magenta/10 px-4 py-1.5 text-sm font-medium text-holo-magenta hover:bg-holo-magenta/20 disabled:opacity-40"
                  >
                    Save draft
                  </button>
                </div>
              </div>

              {drafts.length === 0 && !loading && (
                <p className="text-sm text-holo-dim">No drafts yet.</p>
              )}
              <ul className="flex max-h-44 flex-col gap-2 overflow-y-auto">
                {drafts.map((d) => {
                  const confirmed = confirmText === SEND_CONFIRM_TEXT;
                  return (
                    <li key={d.id} className="rounded-xl border border-holo-border bg-white/[0.03] px-3 py-2">
                      <div className="flex items-center gap-3">
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm text-holo-soft">{d.subject || "(no subject)"}</span>
                          <span className="block truncate text-xs text-holo-muted">to {d.to || "…"}</span>
                        </span>
                        {sending === d.id ? (
                          <span className="font-mono text-[10px] text-holo-muted">Sending…</span>
                        ) : (
                          <button
                            onClick={() => void sendDraft(d)}
                            className="rounded-full border border-holo-danger/40 px-3 py-1 text-[11px] font-medium text-holo-danger hover:bg-holo-danger/10"
                          >
                            Send
                          </button>
                        )}
                      </div>
                      {!confirmed && (
                        <input
                          className="holo-input mt-2 w-full rounded-lg px-3 py-1.5 text-xs outline-none placeholder:text-holo-dim"
                          placeholder={`Type exactly: "${SEND_CONFIRM_TEXT}"`}
                          value={confirmText}
                          onChange={(e) => setConfirmText(e.target.value)}
                        />
                      )}
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </>
      )}

      {error && <p className="text-sm text-holo-danger">{error}</p>}
    </div>
  );
}