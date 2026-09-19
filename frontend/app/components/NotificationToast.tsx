"use client";

import { useEffect, useState } from "react";

export interface ProactiveAlert {
  id: string;
  type: string;
  title: string;
  message: string;
  created_at: string;
  dismissed: boolean;
  metadata?: Record<string, any>;
}

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

interface NotificationToastProps {
  onAskUmi?: (prompt: string) => void;
}

export default function NotificationToast({ onAskUmi }: NotificationToastProps) {
  const [alerts, setAlerts] = useState<ProactiveAlert[]>([]);

  useEffect(() => {
    let eventSource: EventSource | null = null;
    let reconnectTimeout: number | undefined;

    const connectSSE = () => {
      try {
        eventSource = new EventSource(`${BACKEND_URL}/notifications/stream`);

        eventSource.addEventListener("notification", (event) => {
          try {
            const data: ProactiveAlert = JSON.parse(event.data);
            setAlerts((prev) => {
              if (prev.some((a) => a.id === data.id)) return prev;
              return [data, ...prev].slice(0, 3); // keep up to 3 alerts
            });
          } catch (e) {
            console.error("Error parsing notification SSE payload", e);
          }
        });

        eventSource.onerror = () => {
          if (eventSource) {
            eventSource.close();
            eventSource = null;
          }
          // Reconnect after 5 seconds
          reconnectTimeout = window.setTimeout(connectSSE, 5000);
        };
      } catch (err) {
        console.error("Failed to establish notifications SSE connection", err);
      }
    };

    connectSSE();

    return () => {
      if (eventSource) {
        eventSource.close();
      }
      if (reconnectTimeout !== undefined) {
        window.clearTimeout(reconnectTimeout);
      }
    };
  }, []);

  const handleDismiss = async (id: string) => {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
    try {
      await fetch(`${BACKEND_URL}/notifications/${id}/dismiss`, { method: "POST" });
    } catch {
      // Best-effort dismiss
    }
  };

  const handleAction = (alert: ProactiveAlert) => {
    handleDismiss(alert.id);
    if (onAskUmi) {
      onAskUmi(`About your reminder "${alert.message}": what should we do next?`);
    }
  };

  if (alerts.length === 0) {
    return null;
  }

  return (
    <div className="fixed top-6 right-6 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none">
      {alerts.map((alert) => (
        <div
          key={alert.id}
          className="pointer-events-auto entrance-fade rounded-2xl border border-holo-cyan/40 bg-holo-panel/95 p-4 shadow-[0_10px_32px_rgba(0,0,0,0.55)] backdrop-blur-2xl transition-all hover:border-holo-cyan"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="grid h-5 w-5 place-items-center rounded-full bg-holo-cyan/20 text-holo-cyan">
                {alert.type === "calendar_alert" ? (
                  <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                    <line x1="16" y1="2" x2="16" y2="6" />
                    <line x1="8" y1="2" x2="8" y2="6" />
                    <line x1="3" y1="10" x2="21" y2="10" />
                  </svg>
                ) : (
                  <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <polyline points="12 6 12 12 16 14" />
                  </svg>
                )}
              </span>
              <h4 className="font-mono text-xs font-semibold uppercase tracking-wider text-holo-cyan">
                {alert.title}
              </h4>
            </div>
            <button
              type="button"
              onClick={() => handleDismiss(alert.id)}
              className="rounded p-1 text-holo-muted hover:text-white transition-colors"
              title="Dismiss"
            >
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          <p className="mt-2 text-xs font-sans text-holo-text leading-relaxed">
            {alert.message}
          </p>

          <div className="mt-3 flex items-center justify-end gap-2 border-t border-holo-border/40 pt-2.5">
            <button
              type="button"
              onClick={() => handleDismiss(alert.id)}
              className="rounded-lg px-2.5 py-1 font-mono text-[11px] text-holo-muted hover:text-white transition-colors"
            >
              Dismiss
            </button>
            <button
              type="button"
              onClick={() => handleAction(alert)}
              className="rounded-lg border border-holo-cyan/50 bg-holo-cyan/15 px-3 py-1 font-mono text-[11px] font-medium text-holo-cyan hover:bg-holo-cyan/25 transition-all active:scale-95"
            >
              Ask Umi
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
