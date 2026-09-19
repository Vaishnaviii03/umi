import { test } from "node:test";
import assert from "node:assert/strict";
import { hourInRange, idleTriggerDue } from "../app/lib/idle.ts";

const POLICY = {
  enabled: true,
  thresholdSeconds: 45,
  cooldownSeconds: 120,
  maxPromptsPerHour: 4,
  startHour: 8,
  endHour: 23,
};

// 14:00 local, activity at 13:00 (1h idle), no proactive yet.
const BASE = {
  policy: POLICY,
  lastActivityAtMs: Date.UTC(2026, 8, 8, 13, 0, 0),
  lastProactiveAtMs: null,
  proactiveCountLastHour: 0,
};

test("hourInRange covers normal and overnight ranges", () => {
  assert.equal(hourInRange(9, 8, 23), true);
  assert.equal(hourInRange(23, 8, 23), false);
  assert.equal(hourInRange(22, 22, 4), true);
  assert.equal(hourInRange(4, 22, 4), false);
});

test("idle is due after the threshold with no proactive yet", () => {
  const now = Date.UTC(2026, 8, 8, 14, 0, 0);
  const due = idleTriggerDue({ ...BASE, nowMs: now });
  assert.equal(due, true);
});

test("not due while disabled", () => {
  const due = idleTriggerDue({ ...BASE, policy: { ...POLICY, enabled: false } });
  assert.equal(due, false);
});

test("not due without any measured activity", () => {
  const due = idleTriggerDue({ ...BASE, lastActivityAtMs: null });
  assert.equal(due, false);
});

test("not due inside the threshold", () => {
  // Activity 30s before now (100s age assumption below).
  const now = Date.UTC(2026, 8, 8, 14, 0, 0);
  const due = idleTriggerDue({
    ...BASE,
    lastActivityAtMs: Date.UTC(2026, 8, 8, 13, 59, 30),
    nowMs: now,
  });
  assert.equal(due, false);
});

test("not due outside active hours", () => {
  const now = Date.UTC(2026, 8, 8, 2, 0, 0); // 02:00 → outside 8-23
  const due = idleTriggerDue({ ...BASE, nowMs: now });
  assert.equal(due, false);
});

test("due at the start-hour boundary", () => {
  const nowMs = Date.UTC(2026, 8, 8, 8, 0, 0);
  const due = idleTriggerDue({ ...BASE, lastActivityAtMs: Date.UTC(2026, 8, 8, 6, 0, 0), nowMs });
  assert.equal(due, true);
});

test("not due inside the cooldown after a proactive", () => {
  const now = Date.UTC(2026, 8, 8, 14, 0, 0);
  const due = idleTriggerDue({
    ...BASE,
    lastProactiveAtMs: Date.UTC(2026, 8, 8, 13, 59, 0), // 1 min ago
    nowMs: now,
  });
  assert.equal(due, false);
});

test("due again after the cooldown", () => {
  const now = Date.UTC(2026, 8, 8, 14, 10, 0);
  const due = idleTriggerDue({
    ...BASE,
    lastProactiveAtMs: Date.UTC(2026, 8, 8, 14, 7, 0), // 3 min ago
    nowMs: now,
  });
  assert.equal(due, true);
});

test("not due at the hourly cap", () => {
  const now = Date.UTC(2026, 8, 8, 14, 0, 0);
  const due = idleTriggerDue({ ...BASE, proactiveCountLastHour: 4, nowMs: now });
  assert.equal(due, false);
});

test("due below the hourly cap", () => {
  const now = Date.UTC(2026, 8, 8, 14, 0, 0);
  const due = idleTriggerDue({ ...BASE, proactiveCountLastHour: 3, nowMs: now });
  assert.equal(due, true);
});

test("null policy is never due", () => {
  const due = idleTriggerDue({ ...BASE, policy: null });
  assert.equal(due, false);
});