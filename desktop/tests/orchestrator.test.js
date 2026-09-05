"use strict";

const test = require("node:test");
const assert = require("node:assert");
const path = require("path");
const fs = require("fs");

const { STATES } = require("../startup/state-machine");
const { StartupOrchestrator } = require("../startup/orchestrator");
const { MusicPlayer } = require("../startup/music-player");

function quietLogger() {
  return { info() {}, warn() {}, error() {} };
}

function fakeGaurds() {
  return {
    pickGreeting: () => "Good morning. I'm online.",
    bucketForHour: () => "morning",
  };
}

function fakeServices() {
  const backend = { ensureRunning: async () => ({ spawned: true }) };
  const frontend = { ensureRunning: async () => ({ spawned: true }) };
  const stop = () => {};
  backend.stop = stop;
  frontend.stop = stop;
  return { backend, frontend };
}

function failingService() {
  const service = {
    ensureRunning: async () => {
      throw new Error("boom");
    },
    stop: () => {},
  };
  return service;
}

test("orchestrator reaches READY through the full sequence", async () => {
  const { backend, frontend } = fakeServices();
  const states = [];
  const player = { play: async () => ({ started: true }), stop: () => {} };
  const greeting = fakeGaurds();
  const recipient = {
    greeting,
    backend,
    frontend,
    player,
    emit: (e) => states.push(e.state),
    logger: quietLogger(),
  };

  const orchestrator = new StartupOrchestrator(recipient);
  await orchestrator.start();
  assert.strictEqual(orchestrator.stateMachine.current, STATES.READY);
  assert.ok(states.includes(STATES.GREETING));
  assert.strictEqual(states[states.length - 1], STATES.READY);
});

test("music failure degrades gracefully to READY with MEDIA_ERROR", async () => {
  const { backend, frontend } = fakeServices();
  const states = [];
  const failingPlayer = {
    play: async () => {
      throw new Error("no player");
    },
    stop: () => {},
  };
  const orchestrator = new StartupOrchestrator({
    greeting: fakeGaurds(),
    backend,
    frontend,
    player: failingPlayer,
    emit: (e) => states.push(e.state),
    logger: quietLogger(),
  });
  await orchestrator.start();
  assert.strictEqual(orchestrator.stateMachine.current, STATES.READY);
  assert.ok(orchestrator.stateMachine.softErrors.some((e) => e.state === STATES.MEDIA_ERROR));
});

test("backend failure produces INITIALIZATION_ERROR", async () => {
  const frontend = (await fakeServices()).frontend;
  const orchestrator = new StartupOrchestrator({
    greeting: fakeGaurds(),
    backend: failingService(),
    frontend,
    player: { play: async () => ({ started: false }), stop: () => {} },
    emit: () => {},
    logger: quietLogger(),
  });
  await assert.rejects(() => orchestrator.start(), /boom/);
  assert.strictEqual(orchestrator.stateMachine.current, STATES.INITIALIZATION_ERROR);
});

test("music player skips missing file gracefully", async () => {
  const tmp = path.join(require("os").tmpdir(), `umi-music-test-${Date.now()}.mp3`);
  const player = new MusicPlayer({ file: tmp, command: "afplay", logger: quietLogger() });
  const result = await player.play();
  assert.strictEqual(result.started, false);
  assert.strictEqual(result.reason, "file-missing");
  try {
    fs.unlinkSync(tmp);
  } catch {
    /* already gone */
  }
});