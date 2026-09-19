"use strict";

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { app } = require("electron");

class MusicPlayer {
  constructor({ file = "", command = "", logger = console } = {}) {
    this.file = file;
    this.command = command || this._getDefaultPlayerCommand();
    this.logger = logger;
    this._child = null;
  }

  _getDefaultPlayerCommand() {
    if (process.platform === "darwin") return "afplay";
    if (process.platform === "win32") return "powershell.exe"; // uses Start-Process
    return "mpv"; // Linux fallback
  }

  _resolveFilePath(file) {
    if (!file) return null;
    if (path.isAbsolute(file)) return file;
    // Try relative to resources (packaged app)
    const resourcesPath = process.resourcesPath || path.join(__dirname, "..", "..");
    const candidates = [
      file,
      path.join(resourcesPath, file),
      path.join(resourcesPath, "assets", file),
      path.join(__dirname, "..", "..", "assets", file),
      path.join(__dirname, "..", "assets", file),
    ];
    for (const candidate of candidates) {
      if (fs.existsSync(candidate)) return candidate;
    }
    return file; // fallback to original
  }

  isConfigured() {
    const resolved = this._resolveFilePath(this.file);
    return Boolean(this.file) && fs.existsSync(resolved);
  }

  async play() {
    const resolvedFile = this._resolveFilePath(this.file);
    if (!this.file) {
      this.logger.info("startup-music: no track configured — skipping");
      return { started: false, reason: "not-configured" };
    }
    if (!fs.existsSync(resolvedFile)) {
      this.logger.warn(`startup-music: track not found (${resolvedFile}) — skipping`);
      return { started: false, reason: "file-missing" };
    }

    const args = this._getPlayerArgs(this.command, resolvedFile);

    return new Promise((resolve) => {
      const child = spawn(this.command, args, { stdio: "ignore" });
      this._child = child;

      child.on("error", (err) => {
        this.logger.warn(`startup-music: failed to start player (${err.message}) — continuing`);
        this._child = null;
        resolve({ started: false, reason: "player-error" });
      });

      child.on("spawn", () => {
        this.logger.info(`startup-music: started (${resolvedFile})`);
        resolve({ started: true });
      });

      child.on("close", (code) => {
        this._child = null;
        this.logger.info(`startup-music: playback ended (code ${code})`);
      });
    });
  }

  _getPlayerArgs(command, file) {
    if (process.platform === "win32" && command === "powershell.exe") {
      return ["-c", `(New-Object Media.SoundPlayer '${file.replace(/'/g, "''")}').PlaySync()`];
    }
    return [file];
  }

  stop() {
    if (this._child) {
      this._child.kill();
      this._child = null;
    }
  }
}

module.exports = { MusicPlayer };