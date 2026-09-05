"use strict";

const fs = require("fs");
const { spawn } = require("child_process");

class MusicPlayer {
  constructor({ file = "", command = "afplay", logger = console } = {}) {
    this.file = file;
    this.command = command;
    this.logger = logger;
    this._child = null;
  }

  isConfigured() {
    return Boolean(this.file) && fs.existsSync(this.file);
  }

  async play() {
    if (!this.file) {
      this.logger.info("startup-music: no track configured — skipping");
      return { started: false, reason: "not-configured" };
    }
    if (!fs.existsSync(this.file)) {
      this.logger.warn(`startup-music: track not found (${this.file}) — skipping`);
      return { started: false, reason: "file-missing" };
    }

    return new Promise((resolve) => {
      const child = spawn(this.command, [this.file], { stdio: "ignore" });
      this._child = child;

      child.on("error", (err) => {
        this.logger.warn(`startup-music: failed to start player (${err.message}) — continuing`);
        this._child = null;
        resolve({ started: false, reason: "player-error" });
      });

      child.on("spawn", () => {
        this.logger.info(`startup-music: started (${this.file})`);
        resolve({ started: true });
      });

      child.on("close", () => {
        this._child = null;
        this.logger.info("startup-music: playback ended");
      });
    });
  }

  stop() {
    if (this._child) {
      this._child.kill();
      this._child = null;
    }
  }
}

module.exports = { MusicPlayer };