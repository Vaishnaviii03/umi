import { test } from "node:test";
import assert from "node:assert/strict";
import { onNewTurn, onSentenceSpoken, onTurnFinished } from "../app/lib/voice/echoPause.ts";

test("speech pauses the mic only once while voice is active", () => {
  let state = "live";
  const pauses = [];
  const resumes = [];

  const speak = () => {
    const d = onSentenceSpoken(state, true);
    state = d.next;
    if (d.pause) pauses.push("pause");
    if (d.resume) resumes.push("resume");
  };

  // First sentence mutes the mic.
  speak();
  assert.equal(state, "paused");
  assert.deepEqual(pauses, ["pause"]);
  // Second sentence stays muted, no duplicate pause.
  speak();
  assert.deepEqual(pauses, ["pause"]);
});

test("finishing a turn resumes the mic exactly once", () => {
  let state = "paused";
  const calls = [];
  const finish = () => {
    const d = onTurnFinished(state);
    state = d.next;
    if (d.resume) calls.push("resume");
  };
  finish();
  assert.equal(state, "live");
  assert.deepEqual(calls, ["resume"]);
  // A second finish (already live) does not spam resume.
  finish();
  assert.deepEqual(calls, ["resume"]);
});

test("speech does not pause without an active voice session", () => {
  const d = onSentenceSpoken("live", false);
  assert.equal(d.next, "live");
  assert.equal(d.pause, undefined);
});

test("a new turn (thinking) reopens a mic that was muted during speech", () => {
  const d = onNewTurn("paused");
  assert.equal(d.next, "live");
  assert.equal(d.resume, true);
});

test("full loop: live -> paused (speech) -> live (finish), no echo window", () => {
  let state = "live";
  let paused = false;

  const speak = () => {
    const d = onSentenceSpoken(state, true);
    state = d.next;
    if (d.pause) paused = true;
  };
  const finish = () => {
    const d = onTurnFinished(state);
    state = d.next;
    if (d.resume) paused = false;
  };

  speak();
  assert.equal(paused, true, "mic muted while Umi speaks");
  assert.equal(state, "paused");
  finish();
  assert.equal(paused, false, "mic back for the Boss after speech");
  assert.equal(state, "live");
});