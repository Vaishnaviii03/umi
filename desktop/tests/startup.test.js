"use strict";

const test = require("node:test");
const assert = require("node:assert");

const { STATES, StartupStateMachine } = require("../startup/state-machine");
const { pickGreeting } = require("../startup/greeting");

test("flows through the normal startup sequence", () => {
  const sm = new StartupStateMachine();
  const seen = [];
  sm.on("change", ({ to }) => seen.push(to));

  sm.transition(STATES.LAUNCHING);
  sm.transition(STATES.INITIALIZING);
  sm.transition(STATES.LOADING_CONTEXT);
  sm.transition(STATES.READY_TO_GREET);
  sm.transition(STATES.GREETING);
  sm.transition(STATES.STARTUP_MEDIA);
  sm.transition(STATES.READY);

  assert.strictEqual(sm.current, STATES.READY);
  assert.strictEqual(sm.isTerminal, true);
  assert.deepStrictEqual(seen.slice(seen.length - 2), [STATES.STARTUP_MEDIA, STATES.READY]);
});

test("rejects an illegal transition", () => {
  const sm = new StartupStateMachine();
  assert.throws(() => sm.transition(STATES.READY));
});

test("media error degrades to READY", () => {
  const sm = new StartupStateMachine();
  sm.transition(STATES.LAUNCHING);
  sm.transition(STATES.INITIALIZING);
  sm.transition(STATES.LOADING_CONTEXT);
  sm.transition(STATES.READY_TO_GREET);
  sm.transition(STATES.GREETING);
  sm.transition(STATES.STARTUP_MEDIA);
  sm.softError(STATES.MEDIA_ERROR, new Error("boom"));
  sm.transition(STATES.MEDIA_ERROR);
  sm.transition(STATES.READY);
  assert.strictEqual(sm.current, STATES.READY);
  assert.strictEqual(sm.softErrors.length, 1);
});

test("greeting respects time of day buckets", () => {
  const morning = pickGreeting(new Date("2026-09-05T09:00:00"));
  assert.ok(morning.includes("morning"));
  const night = pickGreeting(new Date("2026-09-05T23:00:00"));
  assert.match(night, /late|night/i);
});