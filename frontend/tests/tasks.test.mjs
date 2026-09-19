import { test } from "node:test";
import assert from "node:assert/strict";
import { formatDueLabel, isOverdue, toIsoInput } from "../app/lib/tasks.ts";

test("toIsoInput accepts a date and ISO datetime, rejects blank", () => {
  assert.equal(toIsoInput("2026-09-11"), "2026-09-11");
  assert.equal(toIsoInput("2026-09-11T17:00:00"), "2026-09-11T17:00:00");
  assert.equal(toIsoInput("   "), null);
  assert.equal(toIsoInput("nonsense"), null);
});

test("formatDueLabel returns null for no/invalid date", () => {
  assert.equal(formatDueLabel(null), null);
  assert.equal(formatDueLabel("garbage"), null);
});

test("formatDueLabel names today, tomorrow, yesterday", () => {
  const now = new Date(2026, 8, 8, 12, 0); // Sep 8 2026, local noon
  assert.equal(formatDueLabel("2026-09-08T09:00:00", now), "Today · 9:00 AM");
  assert.equal(formatDueLabel("2026-09-09T09:00:00", now), "Tomorrow · 9:00 AM");
  assert.equal(formatDueLabel("2026-09-07T09:00:00", now), "Yesterday · 9:00 AM");
});

test("formatDueLabel shows a short date for farther dates", () => {
  const now = new Date(2026, 8, 8, 12, 0);
  const label = formatDueLabel("2026-09-20T09:00:00", now);
  assert.ok(label && label.startsWith("Sep 20"), `got ${label}`);
});

test("isOverdue compares against the moment", () => {
  const now = new Date(2026, 8, 8, 12, 0);
  assert.equal(isOverdue("2026-09-08T11:00:00", now), true);
  assert.equal(isOverdue("2026-09-08T13:00:00", now), false);
  assert.equal(isOverdue(null, now), false);
});