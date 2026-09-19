import { test } from "node:test";
import assert from "node:assert/strict";
import { isInterruptionPhrase } from "../app/lib/voice/turn.ts";

test("isInterruptionPhrase detects direct stop commands", () => {
  assert.equal(isInterruptionPhrase("stop"), true);
  assert.equal(isInterruptionPhrase("Stop"), true);
  assert.equal(isInterruptionPhrase("STOP!"), true);
  assert.equal(isInterruptionPhrase("umi stop"), true);
  assert.equal(isInterruptionPhrase("Umi stop"), true);
  assert.equal(isInterruptionPhrase("stop umi"), true);
  assert.equal(isInterruptionPhrase("stop please"), true);
  assert.equal(isInterruptionPhrase("please stop"), true);
  assert.equal(isInterruptionPhrase("stop it"), true);
  assert.equal(isInterruptionPhrase("stop now"), true);
});

test("isInterruptionPhrase detects pause, wait, and quiet commands", () => {
  assert.equal(isInterruptionPhrase("wait"), true);
  assert.equal(isInterruptionPhrase("umi wait"), true);
  assert.equal(isInterruptionPhrase("hold on"), true);
  assert.equal(isInterruptionPhrase("umi hold on"), true);
  assert.equal(isInterruptionPhrase("pause"), true);
  assert.equal(isInterruptionPhrase("quiet"), true);
  assert.equal(isInterruptionPhrase("be quiet"), true);
  assert.equal(isInterruptionPhrase("shh"), true);
  assert.equal(isInterruptionPhrase("stop talking"), true);
});

test("isInterruptionPhrase ignores general conversational queries", () => {
  assert.equal(isInterruptionPhrase("what is the weather today"), false);
  assert.equal(isInterruptionPhrase("how do I configure a database in postgresql"), false);
  assert.equal(isInterruptionPhrase("can you tell me a story about a dragon"), false);
  assert.equal(isInterruptionPhrase(""), false);
  assert.equal(isInterruptionPhrase("hello umi"), false);
});
