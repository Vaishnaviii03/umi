import { test } from "node:test";
import assert from "node:assert/strict";
import { chatRequestBody } from "../app/lib/chat.ts";

test("chat request body carries voice:true for voice turns", () => {
  assert.deepEqual(chatRequestBody("what time is it?", null, true), {
    message: "what time is it?",
    conversation_id: null,
    voice: true,
    proactive: false,
  });
});

test("chat request body defaults voice to false for text turns", () => {
  assert.deepEqual(chatRequestBody("hello", "conv-1", false), {
    message: "hello",
    conversation_id: "conv-1",
    voice: false,
    proactive: false,
  });
});