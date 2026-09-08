import { test } from "node:test";
import assert from "node:assert/strict";
import {
  SESSION_STORAGE_KEY,
  chatRequestBody,
  isUuidLike,
  parseSessionResponse,
  readStoredConversationId,
  storeConversationId,
} from "../app/lib/chat.ts";

test("chatRequestBody carries conversation id and voice flag", () => {
  assert.deepEqual(chatRequestBody("hi", "cafebebe-0000-0000-0000-000000000001", true), {
    message: "hi",
    conversation_id: "cafebebe-0000-0000-0000-000000000001",
    voice: true,
  });
  assert.deepEqual(chatRequestBody("hi", null, false), {
    message: "hi",
    conversation_id: null,
    voice: false,
  });
});

test("isUuidLike accepts a canonical uuid and rejects garbage", () => {
  assert.equal(isUuidLike("cafebebe-0000-0000-0000-000000000001"), true);
  assert.equal(isUuidLike("not-a-uuid"), false);
  assert.equal(isUuidLike(""), false);
  assert.equal(isUuidLike(null), false);
});

test("readStoredConversationId returns a stored uuid", () => {
  const storage = { getItem: () => "cafebebe-0000-0000-0000-000000000001" };
  assert.equal(readStoredConversationId(storage), "cafebebe-0000-0000-0000-000000000001");
});

test("readStoredConversationId ignores absent or malformed values", () => {
  assert.equal(readStoredConversationId({ getItem: () => null }), null);
  assert.equal(readStoredConversationId({ getItem: () => "junk" }), null);
  assert.equal(readStoredConversationId(null), null);
});

test("storeConversationId writes and clears the key", () => {
  let value = null;
  const storage = {
    setItem: (_k, v) => (value = v),
    removeItem: () => (value = null),
  };
  storeConversationId(storage, "cafebebe-0000-0000-0000-000000000001");
  assert.equal(value, "cafebebe-0000-0000-0000-000000000001");
  storeConversationId(storage, null);
  assert.equal(value, null);
});

test("parseSessionResponse extracts the resume fields", () => {
  const parsed = parseSessionResponse({
    conversation_id: "abc-123",
    resumed: true,
    greeting: { owed: true, new: false },
    idle: { enabled: true, threshold_seconds: 45, cooldown_seconds: 120 },
    server_time: "now",
  });
  assert.equal(parsed.conversationId, "abc-123");
  assert.equal(parsed.resumed, true);
  assert.equal(parsed.greetingOwed, true);
  assert.equal(parsed.greetingNew, false);
  assert.deepEqual(parsed.idle, { enabled: true, thresholdSeconds: 45, cooldownSeconds: 120 });
});

test("parseSessionResponse degrades on malformed or absent payload", () => {
  const parsed = parseSessionResponse(null);
  assert.equal(parsed.conversationId, null);
  assert.equal(parsed.resumed, false);
  assert.equal(parsed.greetingOwed, false);
  assert.equal(parsed.idle, null);
  const partial = parseSessionResponse({ conversation_id: 42 });
  assert.equal(partial.conversationId, null);
  assert.equal(partial.idle, null);
});

test("SESSION_STORAGE_KEY is namespaced to umi", () => {
  assert.equal(SESSION_STORAGE_KEY, "umi_conversation_id");
});