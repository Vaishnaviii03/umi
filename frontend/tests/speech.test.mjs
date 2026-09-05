import { test } from "node:test";
import assert from "node:assert/strict";
import {
  FALLBACK_SPEAK_MS,
  MAX_TTS_CHARS,
  VOICE_UNAVAILABLE_MESSAGE,
  isSentenceComplete,
  normalizeTtsText,
  popCompletedSentences,
  splitSentences,
} from "../app/lib/speech.ts";

test("normalizeTtsText trims surrounding whitespace", () => {
  assert.equal(normalizeTtsText("  hello  "), "hello");
});

test("normalizeTtsText returns empty string for blank input", () => {
  assert.equal(normalizeTtsText("   "), "");
  assert.equal(normalizeTtsText(""), "");
});

test("normalizeTtsText caps text at MAX_TTS_CHARS", () => {
  const long = "a".repeat(5000);
  assert.equal(normalizeTtsText(long).length, MAX_TTS_CHARS);
});

test("voice unavailable message is graceful and free of internals", () => {
  assert.match(VOICE_UNAVAILABLE_MESSAGE, /voice unavailable/i);
  assert.doesNotMatch(VOICE_UNAVAILABLE_MESSAGE, /api.?key/i);
  assert.doesNotMatch(VOICE_UNAVAILABLE_MESSAGE, /401|500|trace/i);
});

test("fallback speak duration is a positive sane value", () => {
  assert.ok(FALLBACK_SPEAK_MS > 0 && FALLBACK_SPEAK_MS < 3000);
});

test("splitSentences splits on sentence-ending punctuation", () => {
  assert.deepEqual(splitSentences("Hello there! How are you? Fine."), [
    "Hello there!",
    "How are you?",
    "Fine.",
  ]);
});

test("splitSentences keeps a trailing partial clause intact", () => {
  assert.deepEqual(splitSentences("Hi. How are"), ["Hi.", "How are"]);
});

test("splitSentences handles empty/blank input", () => {
  assert.deepEqual(splitSentences(""), []);
  assert.deepEqual(splitSentences("   "), []);
});

test("isSentenceComplete checks terminal punctuation", () => {
  assert.equal(isSentenceComplete("Yes."), true);
  assert.equal(isSentenceComplete("Why?"), true);
  assert.equal(isSentenceComplete("Indeed!"), true);
  assert.equal(isSentenceComplete("And so"), false);
});

test("popCompletedSentences separates finished sentences from the remainder", () => {
  const { complete, remainder } = popCompletedSentences("Hi there. How are you today? Still thinking");
  assert.deepEqual(complete, ["Hi there.", "How are you today?"]);
  assert.equal(remainder, "Still thinking");
});

test("popCompletedSentences leaves unfinished text buffered", () => {
  const { complete, remainder } = popCompletedSentences("No punctuation yet");
  assert.deepEqual(complete, []);
  assert.equal(remainder, "No punctuation yet");
});