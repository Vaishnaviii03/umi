import { test } from "node:test";
import assert from "node:assert/strict";
import {
  GOOGLE_SERVICES,
  reauthorizeMessage,
  servicesCovered,
} from "../app/lib/gmail.ts";

const G = (p) => `https://www.googleapis.com/auth/${p}`;

const ALL_SCOPES = [G("gmail.modify"), G("calendar.readonly"), G("calendar.events"), G("drive"), G("spreadsheets"), G("documents"), G("youtube")];

function status(partial) {
  return {
    connected: false,
    email: null,
    granted_scopes: [],
    required_scopes: ALL_SCOPES,
    needs_reauthorization: false,
    ...partial,
  };
}

test("GOOGLE_SERVICES enumerates all six capabilities in order", () => {
  assert.deepEqual([...GOOGLE_SERVICES], ["Gmail", "Calendar", "Drive", "Sheets", "Docs", "YouTube"]);
});

test("servicesCovered: none when disconnected or missing status", () => {
  assert.deepEqual(servicesCovered(null), []);
  assert.deepEqual(servicesCovered(status({ connected: false })), []);
});

test("servicesCovered: all six when the token grants every scope", () => {
  assert.deepEqual(
    servicesCovered(status({ connected: true, granted_scopes: ALL_SCOPES })),
    ["Gmail", "Calendar", "Drive", "Sheets", "Docs", "YouTube"],
  );
});

test("servicesCovered: old 3-scope token covers only Gmail + Calendar", () => {
  const old = [G("gmail.modify"), G("calendar.readonly"), G("calendar.events")];
  assert.deepEqual(servicesCovered(status({ connected: true, granted_scopes: old })), ["Gmail", "Calendar"]);
});

test("servicesCovered: gmail-only token covers just Gmail", () => {
  assert.deepEqual(servicesCovered(status({ connected: true, granted_scopes: [G("gmail.modify")] })), ["Gmail"]);
});

test("reauthorizeMessage: null when everything is covered", () => {
  assert.equal(reauthorizeMessage(status({ connected: true, granted_scopes: ALL_SCOPES })), null);
});

test("reauthorizeMessage: null when disconnected", () => {
  assert.equal(reauthorizeMessage(status({ connected: false })), null);
});

test("reauthorizeMessage: names the missing services", () => {
  const old = [G("gmail.modify"), G("calendar.readonly"), G("calendar.events")];
  const msg = reauthorizeMessage(status({ connected: true, granted_scopes: old, needs_reauthorization: true }));
  assert.equal(msg, "Reconnect to enable Drive, Sheets, Docs, YouTube");
});

test("reauthorizeMessage: only lists what is actually missing", () => {
  const partial = [G("gmail.modify"), G("drive"), G("documents")];
  const msg = reauthorizeMessage(status({ connected: true, granted_scopes: partial, needs_reauthorization: true }));
  assert.equal(msg, "Reconnect to enable Calendar, Sheets, YouTube");
});