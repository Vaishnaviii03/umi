"use strict";

const path = require("path");
require("dotenv").config({ path: path.resolve(__dirname, ".env") });

const config = Object.freeze({
  host: "127.0.0.1",
  frontendPort: Number(process.env.UMI_FRONTEND_PORT || 3456),
  backendPort: Number(process.env.UMI_BACKEND_PORT || 8000),
  frontendUrl: process.env.UMI_FRONTEND_URL || `http://127.0.0.1:${Number(process.env.UMI_FRONTEND_PORT || 3456)}`,
  backendUrl: process.env.UMI_BACKEND_URL || `http://127.0.0.1:${Number(process.env.UMI_BACKEND_PORT || 8000)}`,
  frontendDir: process.env.UMI_FRONTEND_DIR || path.resolve(__dirname, "..", "frontend"),
  backendDir: process.env.UMI_BACKEND_DIR || path.resolve(__dirname, "..", "backend"),
  musicFile: process.env.UMI_MUSIC_FILE || path.join(__dirname, "..", "assets", "startup.wav"),
  musicCommand: process.env.UMI_MUSIC_COMMAND || "",
  startupTimeoutMs: Number(process.env.UMI_STARTUP_TIMEOUT_MS || 90000),
});

module.exports = { config };