/**
 * Pure idle/proactive timing helpers (browser side). The backend is the final
 * authority — these just decide when to ASK, mirroring the server's policy so
 * the frontend does not hammer the endpoint between thresholds.
 */

export type IdlePolicy = {
  enabled: boolean;
  thresholdSeconds: number;
  cooldownSeconds: number;
  maxPromptsPerHour: number;
  startHour: number;
  endHour: number;
};

/** True when `hour` is within [start, end), supporting overnight ranges. */
export function hourInRange(hour: number, start: number, end: number): boolean {
  if (start <= end) return start <= hour && hour < end;
  return hour >= start || hour < end;
}

export type IdleInput = {
  policy: IdlePolicy | null;
  lastActivityAtMs: number | null;
  lastProactiveAtMs: number | null;
  proactiveCountLastHour: number;
  nowMs?: number;
};

/** Whether Umi should open a proactive conversation right now. */
export function idleTriggerDue(input: IdleInput): boolean {
  const { policy, lastActivityAtMs, lastProactiveAtMs, proactiveCountLastHour } = input;
  const now = input.nowMs ?? Date.now();
  if (!policy || !policy.enabled) return false;
  if (lastActivityAtMs === null) return false;
  const ageSec = (now - lastActivityAtMs) / 1000;
  if (ageSec < policy.thresholdSeconds) return false;
  if (!hourInRange(new Date(now).getHours(), policy.startHour, policy.endHour)) return false;
  if (lastProactiveAtMs !== null && (now - lastProactiveAtMs) / 1000 < policy.cooldownSeconds) {
    return false;
  }
  if (proactiveCountLastHour >= policy.maxPromptsPerHour) return false;
  return true;
}