"use strict";

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

async function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function isHealthy(url, timeoutMs = 1500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${url}/health`, { signal: controller.signal });
    if (!res.ok) return false;
    const body = await res.json();
    return body && body.status === "ok";
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

function resolvePythonBinary(backendDir) {
  const candidates =
    process.platform === "win32"
      ? [
          path.join(backendDir, ".venv", "Scripts", "python.exe"),
          path.join(backendDir, "venv", "Scripts", "python.exe"),
        ]
      : [
          path.join(backendDir, ".venv", "bin", "python"),
          path.join(backendDir, "venv", "bin", "python"),
        ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || "python";
}

class BackendService {
  constructor({
    url = "http://127.0.0.1:8000",
    backendDir = path.resolve(__dirname, "..", "..", "backend"),
    port = 8000,
    logger = console,
  } = {}) {
    this.url = url;
    this.backendDir = backendDir;
    this.port = port;
    this.logger = logger;
    this._child = null;
  }

  async ensureRunning({ timeoutMs = 30000 } = {}) {
    if (await isHealthy(this.url)) {
      this.logger.info(`backend: already healthy at ${this.url}`);
      return { spawned: false };
    }

    this.logger.info("backend: not running — starting it");
    this._spawn();
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (await isHealthy(this.url)) {
        this.logger.info(`backend: healthy at ${this.url}`);
        return { spawned: true };
      }
      await wait(500);
    }
    throw new Error(`backend failed to become healthy within ${timeoutMs}ms`);
  }

  _spawn() {
    const python = resolvePythonBinary(this.backendDir);
    const args = ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(this.port)];
    this.logger.info(`backend: spawning ${python} ${args.join(" ")}`);
    const child = spawn(python, args, { cwd: this.backendDir, stdio: ["ignore", "pipe", "pipe"] });
    this._child = child;

    const prefix = "backend:";
    if (child.stdout) child.stdout.on("data", (d) => this.logger.info(`${prefix} ${String(d).trimEnd()}`));
    if (child.stderr) child.stderr.on("data", (d) => this.logger.warn(`${prefix} ${String(d).trimEnd()}`));
    child.on("exit", (code) => {
      this.logger.info(`backend: process exited (code=${code})`);
      this._child = null;
    });
  }

  stop() {
    if (this._child && !this._child.killed) {
      this.logger.info("backend: stopping process");
      this._child.kill();
    }
  }
}

module.exports = { BackendService, isHealthy, resolvePythonBinary };