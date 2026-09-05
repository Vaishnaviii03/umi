import { test } from "node:test";
import assert from "node:assert/strict";
import {
  MIN_TRANSCRIPT_CHARS,
  isDuplicateCommit,
  isMeaningfulTranscript,
  normalizeTranscript,
} from "../app/lib/voice/turn.ts";

test("normalizeTranscript collapses whitespace and trims", () => {
  assert.equal(normalizeTranscript("  what   time   is   it  "), "what time is it");
  assert.equal(normalizeTranscript(""), "");
});

test("isMeaningfulTranscript rejects blank transcripts", () => {
  assert.equal(isMeaningfulTranscript("   "), false);
  assert.equal(isMeaningfulTranscript(""), false);
  assert.equal(isMeaningfulTranscript("hi"), MIN_TRANSCRIPT_CHARS >= 1);
});

test("isDuplicateCommit detects exact repeats", () => {
  assert.equal(isDuplicateCommit("Hello Umi", "Hello Umi"), true);
  assert.equal(isDuplicateCommit("Hello Umi", "hello umi"), true);
});

test("isDuplicateCommit ignores whitespace differences", () => {
  assert.equal(isDuplicateCommit(" hello  umi ", "hello  umi"), true);
});

test("isDuplicateCommit allows distinct utterances", () => {
  assert.equal(isDuplicateCommit("What time is it", "Tell me a joke"), false);
});

test("isDuplicateCommit treats empty previous as never a duplicate", () => {
  assert.equal(isDuplicateCommit("", "Anything"), false);
});