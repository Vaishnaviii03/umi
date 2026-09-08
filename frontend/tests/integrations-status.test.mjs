import { test } from "node:test";
import assert from "node:assert/strict";
import {
  integrationActive,
  integrationLabel,
  integrationStatusLabel,
  INTEGRATION_PLATFORMS,
} from "../app/lib/integrations.ts";

test("integrationLabel maps both platforms", () => {
  assert.equal(integrationLabel("discord"), "Discord");
  assert.equal(integrationLabel("telegram"), "Telegram");
  assert.deepEqual([...INTEGRATION_PLATFORMS], ["discord", "telegram"]);
});

test("integrationActive is true only for enabled, healthy integrations", () => {
  assert.equal(integrationActive(null), false);
  assert.equal(integrationActive(undefined), false);
  assert.equal(integrationActive({ enabled: false, status: "connected", detail: null }), false);
  assert.equal(integrationActive({ enabled: true, status: "disabled", detail: null }), false);
  assert.equal(integrationActive({ enabled: true, status: "error", detail: "bad token" }), false);
  assert.equal(integrationActive({ enabled: true, status: "connected", detail: null }), true);
  assert.equal(integrationActive({ enabled: true, status: "reconnecting", detail: null }), true);
});

test("integrationStatusLabel describes the connection state", () => {
  assert.equal(integrationStatusLabel(null), "off");
  assert.equal(integrationStatusLabel({ enabled: false, status: "disabled", detail: null }), "off");
  assert.equal(integrationStatusLabel({ enabled: true, status: "connected", detail: null }), "connected");
  assert.equal(integrationStatusLabel({ enabled: true, status: "reconnecting", detail: null }), "reconnecting");
  assert.equal(integrationStatusLabel({ enabled: true, status: "error", detail: "invalid" }), "error");
});