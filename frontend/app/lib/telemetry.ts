/**
 * Lightweight development latency tracing.
 *
 * Logs per-turn latency timings (stt_commit_ms, total_turn_latency_ms, …)
 * to the console in dev so bottlenecks are visible without any production
 * cost. Pure/no-DOM so it can be unit-tested in Node.
 */

export type LatencyMetric = number | string;

export type LatencyTrace = Record<string, LatencyMetric>;

/** Monotonic clock in ms (performance.now in the browser, Date.now fallback). */
export function nowMs(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

export function traceLatency(metrics: LatencyTrace): void {
  if (typeof process !== "undefined" && process.env?.NODE_ENV === "production") return;
  const entries = Object.entries(metrics)
    .map(([k, v]) => `${k}=${v}`)
    .join(" ");
  if (typeof console !== "undefined") {
    console.debug(`[umi-latency] ${entries}`);
  }
}