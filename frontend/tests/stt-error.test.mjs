import { test } from "node:test";
import assert from "node:assert/strict";
import {
  VOICE_CONNECTION_LOST,
  VOICE_CREDITS_EXHAUSTED,
  mapSttErrorMessage,
} from "../app/lib/voice/stt.ts";

test("quota_exceeded message maps to the credits message", () => {
  assert.equal(
    mapSttErrorMessage({ message_type: "quota_exceeded", error: "You have exceeded your quota." }),
    VOICE_CREDITS_EXHAUSTED,
  );
});

test("billing/funds-related error text maps to the credits message", () => {
  assert.equal(
    mapSttErrorMessage({ message_type: "error", error: "insufficient_funds_initial_check" }),
    VOICE_CREDITS_EXHAUSTED,
  );
  assert.equal(
    mapSttErrorMessage({ message_type: "error", error: "You have no more credits left." }),
    VOICE_CREDITS_EXHAUSTED,
  );
});

test("connection errors keep the generic message", () => {
  assert.equal(mapSttErrorMessage({ message_type: "auth_error", error: "bad token" }), VOICE_CONNECTION_LOST);
  assert.equal(mapSttErrorMessage({ message_type: "transcriber_error", error: "burst" }), VOICE_CONNECTION_LOST);
  assert.equal(mapSttErrorMessage(new Error("WebSocket closed unexpectedly")), VOICE_CONNECTION_LOST);
  assert.equal(mapSttErrorMessage(undefined), VOICE_CONNECTION_LOST);
  assert.equal(mapSttErrorMessage("generic"), VOICE_CONNECTION_LOST);
});