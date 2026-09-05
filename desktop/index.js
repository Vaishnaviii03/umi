"use strict";

const path = require("path");
const { app, BrowserWindow, Menu, session } = require("electron");

const { config } = require("./config");
const { StartupStateMachine } = require("./startup/state-machine");
const { StartupOrchestrator } = require("./startup/orchestrator");
const { pickGreeting, bucketForHour } = require("./startup/greeting");
const { MusicPlayer } = require("./startup/music-player");
const { BackendService } = require("./services/backend");
const { FrontendService } = require("./services/frontend");

let mainWindow = null;
let orchestrator = null;
let quitting = false;

function emitStartupState(event) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("umi:startup-state", event);
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1080,
    height: 760,
    minWidth: 480,
    minHeight: 620,
    title: "Umi",
    show: false,
    backgroundColor: "#09090b",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.on("closed", () => {
    mainWindow = null;
    if (!quitting) {
      app.quit();
    }
  });

  const menu = process.platform === "darwin" ? Menu.buildFromTemplate([]) : null;
  if (menu) Menu.setApplicationMenu(menu);
}

async function runStartup() {
  const stateMachine = new StartupStateMachine();
  orchestrator = new StartupOrchestrator({
    stateMachine,
    backend: new BackendService({
      url: config.backendUrl,
      backendDir: config.backendDir,
      port: config.backendPort,
    }),
    frontend: new FrontendService({
      url: config.frontendUrl,
      frontendDir: config.frontendDir,
      port: config.frontendPort,
    }),
    greeting: { pickGreeting, bucketForHour },
    player: new MusicPlayer({
      file: config.musicFile,
      command: config.musicCommand,
    }),
    emit: emitStartupState,
  });

  try {
    await orchestrator.start();
  } catch (err) {
    console.error(`startup failed: ${err.message}`);
  }
}

app.whenReady().then(async () => {
  // Grant microphone access so the continuous voice session (realtime STT)
  // can open the mic without a system dialog on every launch.
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    if (permission === "media" || permission === "mediaKeySystem") {
      callback(true);
      return;
    }
    callback(false);
  });
  session.defaultSession.setDevicePermissionHandler(() => true);

  createWindow();
  await runStartup();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", () => {
  quitting = true;
  if (orchestrator) orchestrator.stop();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});