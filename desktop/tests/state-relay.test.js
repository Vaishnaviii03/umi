"use strict";

const test = require("node:test");
const assert = require("node:assert");

const { StartupStateRelay } = require("../startup/state-relay");

function quietLogger() {
  return { info() {}, warn() {}, error() {} };
}

test("relay forwards events and buffers the last one", () => {
  const sent = [];
  const relay = new StartupStateRelay({ send: (e) => sent.push(e), logger: quietLogger() });
  relay.emit({ state: "LAUNCHING" });
  relay.emit({ state: "GREETING", greeting: "Good morning." });
  assert.deepStrictEqual(sent.map((e) => e.state), ["LAUNCHING", "GREETING"]);
  assert.deepStrictEqual(relay.current(), { state: "GREETING", greeting: "Good morning." });
});

test("replay re-sends only the buffer, not the whole history", () => {
  const sent = [];
  const relay = new StartupStateRelay({ send: (e) => sent.push(e), logger: quietLogger() });
  relay.emit({ state: "LAUNCHING" });
  relay.emit({ state: "GREETING", greeting: "Hello." });
  relay.replay();
  assert.strictEqual(sent.length, 3);
  assert.deepStrictEqual(sent[2], { state: "GREETING", greeting: "Hello." });
});

test("replay with no buffered event is a no-op", () => {
  const sent = [];
  const relay = new StartupStateRelay({ send: (e) => sent.push(e), logger: quietLogger() });
  assert.strictEqual(relay.replay(), null);
  assert.strictEqual(relay.current(), null);
  assert.strictEqual(sent.length, 0);
});

test("an ACK after the full sequence replays the final state", () => {
  const sent = [];
  const relay = new StartupStateRelay({ send: (e) => sent.push(e), logger: quietLogger() });
  relay.emit({ state: "GREETING", greeting: "Good evening, Boss." });
  relay.emit({ state: "READY" });
  const replayed = relay.replay();
  assert.deepStrictEqual(replayed, { state: "READY" });
});