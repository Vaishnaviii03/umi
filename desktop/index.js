"use strict";

const path = require("path");
const { app, BrowserWindow, Menu, session, ipcMain } = require("electron");
const net = require("node:net"); // Node's socket module (Electron's `net` is HTTP-only)
const fs = require("fs");

const { config } = require("./config");
const { StartupStateMachine } = require("./startup/state-machine");
const { StartupOrchestrator } = require("./startup/orchestrator");
const { StartupStateRelay } = require("./startup/state-relay");
const { pickGreeting, pickFullGreeting, bucketForHour } = require("./startup/greeting");
const { MusicPlayer } = require("./startup/music-player");
const { BackendService } = require("./services/backend");
const { FrontendService } = require("./services/frontend");

let mainWindow = null;
let orchestrator = null;
let quitting = false;
let ipcServer = null;
let startupRelay = null;

// Single instance lock
const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
  console.log("Another instance is already running. Exiting.");
  app.quit();
  process.exit(0);
}

app.on("second-instance", () => {
  // Someone tried to run a second instance, focus the main window instead
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
    mainWindow.show();
  }
});

// IPC server for launcher activation
function startIPCServer() {
  const IPC_SOCKET_PATH = "/tmp/umi_launcher_ipc.sock";

  try {
    // Clean up any existing socket
    try { fs.unlinkSync("/tmp/umi_launcher_ipc.sock"); } catch (e) {}

    const server = net.createServer((socket) => {
      socket.on("data", (data) => {
        if (data && data.includes("UMI_ACTIVATE")) {
          console.log("Activation signal received from launcher");
          if (mainWindow) {
            if (mainWindow.isMinimized()) mainWindow.restore();
            mainWindow.focus();
            mainWindow.show();
          }
        }
      });
    });

    server.on("error", (err) => {
      console.error("IPC server error:", err);
    });

    // Clean up old socket
    try { fs.unlinkSync("/tmp/umi_launcher_ipc.sock"); } catch (e) {}

    server.listen("/tmp/umi_launcher_ipc.sock", () => {
      console.log("Umi desktop IPC server listening for launcher activation");
    });
  } catch (err) {
    console.error("Failed to start IPC server:", err);
  }
}

function emitStartupState(event) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("umi:startup-state", event);
  }
}

function setupStartupRelayIpc() {
  // The renderer signals once it registered its listener (hydration done) so a
  // GREETING payload that was sent too early is not lost.
  ipcMain.on("umi:startup-ready", () => {
    startupRelay && startupRelay.replay();
  });
  // Pull-based fallback: the renderer can also read the current state directly.
  ipcMain.handle("umi:startup-state:get", () => {
    return startupRelay ? startupRelay.current() : null;
  });
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
  startupRelay = new StartupStateRelay({ send: emitStartupState });
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
    greeting: { pickGreeting, pickFullGreeting, bucketForHour },
    player: new MusicPlayer({
      file: config.musicFile,
      command: config.musicCommand,
    }),
    emit: (event) => startupRelay.emit(event),
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

  // Start IPC server for launcher activation
  startIPCServer();

  setupStartupRelayIpc();

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