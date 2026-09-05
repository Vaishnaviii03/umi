"use strict";

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

async function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function isServing(url, timeoutMs = 1500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

function resolveNextBinary(frontendDir) {
  const candidates =
    process.platform === "win32"
      ? [path.join(frontendDir, "node_modules", ".bin", "next.cmd")]
      : [path.join(frontendDir, "node_modules", ".bin", "next")];
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (found) return { command: found, args: [] };
  return {
    command: process.platform === "win32" ? "npm.cmd" : "npm",
    args: ["exec", "--", "next"],
  };
}

function hasProductionBuild(frontendDir) {
  return fs.existsSync(path.join(frontendDir, ".next", "BUILD_ID"));
}

class FrontendService {
  constructor({
    url = "http://127.0.0.1:3456",
    frontendDir = path.resolve(__dirname, "..", "..", "frontend"),
    port = 3456,
    logger = console,
  } = {}) {
    this.url = url;
    this.frontendDir = frontendDir;
    this.port = port;
    this.logger = logger;
    this._child = null;
  }

  async ensureRunning({ timeoutMs = 60000 } = {}) {
    if (await isServing(this.url)) {
      this.logger.info(`frontend: already serving at ${this.url}`);
      return { spawned: false, dev: false };
    }

    const useDev = !hasProductionBuild(this.frontendDir);
    this.logger.info(`frontend: not serving — starting next ${useDev ? "(dev)" : "(production)"}`);
    this._spawn(useDev);

    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (await isServing(this.url)) {
        this.logger.info(`frontend: serving at ${this.url}`);
        return { spawned: true, dev: useDev };
      }
      await wait(750);
    }
    throw new Error(`frontend failed to start within ${timeoutMs}ms`);
  }

  _spawn(useDev) {
    const { command, args } = resolveNextBinary(this.frontendDir);
    const fullArgs = useDev
      ? [...args, "dev", "--hostname", "127.0.0.1", "--port", String(this.port)]
      : [...args, "start", "--hostname", "127.0.0.1", "--port", String(this.port)];
    this.logger.info(`frontend: spawning ${command} ${fullArgs.join(" ")}`);
    const child = spawn(command, fullArgs, {
      cwd: this.frontendDir,
      stdio: ["ignore", "pipe", "pipe"],
      shell: process.platform === "win32",
    });
    this._child = child;

    const prefix = "frontend:";
    if (child.stdout) child.stdout.on("data", (d) => this.logger.info(`${prefix} ${String(d).trimEnd()}`));
    if (child.stderr) child.stderr.on("data", (d) => this.logger.warn(`${prefix} ${String(d).trimEnd()}`));
    child.on("exit", (code) => {
      this.logger.info(`frontend: process exited (code=${code})`);
      this._child = null;
    });
  }

  stop() {
    if (this._child && !this._child.killed) {
      this.logger.info("frontend: stopping process");
      this._child.kill();
    }
  }
}

module.exports = { FrontendService, isServing, resolveNextBinary, hasProductionBuild };