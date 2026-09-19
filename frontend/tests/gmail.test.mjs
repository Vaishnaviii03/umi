import { test } from "node:test";
import assert from "node:assert/strict";
import { connectErrorMessage, fromLabel, timeAgo, GmailNotConnected, GmailUnavailable } from "../app/lib/gmail.ts";

test("timeAgo returns short relative labels", () => {
  const now = new Date(2026, 8, 8, 12, 0); // local time; offsets keep TZ-agnostic
  const ago = (ms) => new Date(now.getTime() - ms).toISOString();
  assert.equal(timeAgo(ago(30_000), now), "now");
  assert.equal(timeAgo(ago(5 * 60_000), now), "5m");
  assert.equal(timeAgo(ago(3 * 60 * 60_000), now), "3h");
  assert.equal(timeAgo(ago(2 * 24 * 60 * 60_000), now), "2d");
  assert.equal(timeAgo(null, now), "");
  assert.equal(timeAgo("garbage", now), "");
});

test("fromLabel prefers the name, falls back to address", () => {
  assert.equal(fromLabel({ id: "1", subject: "", from_name: "Alice", from_email: "a@b.com" }), "Alice");
  assert.equal(fromLabel({ id: "1", subject: "", from_email: "a@b.com" }), "a@b.com");
  assert.equal(fromLabel({ id: "1", subject: "", from_header: "Bob <b@c.com>" }), "b@c.com");
  assert.equal(fromLabel({ id: "1", subject: "" }), "Unknown");
});

test("gmail error classes exist", () => {
  assert.ok(new GmailNotConnected() instanceof Error);
  assert.ok(new GmailUnavailable() instanceof Error);
});

test("connectErrorMessage maps OAuth callback params", () => {
  assert.equal(connectErrorMessage("?gmail=error&error=denied"), "Google sign-in was cancelled.");
  assert.equal(connectErrorMessage("?gmail=error&error=access_denied"), "Google sign-in was cancelled.");
  assert.equal(connectErrorMessage("?gmail=error&error=auth-failed"), "Google sign-in failed on Umi's side. Please try again.");
  assert.equal(connectErrorMessage("?gmail=error&error=weird"), "Google sign-in failed.");
  assert.equal(connectErrorMessage("?gmail=connected"), null);
  assert.equal(connectErrorMessage(""), null);
});