"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("umi", {
  platform: process.platform,
  onStartupState: (callback) =>
    ipcRenderer.on("umi:startup-state", (_event, payload) => callback(payload)),
  /** Pull the current startup state instead of waiting for a push. */
  getStartupState: () => ipcRenderer.invoke("umi:startup-state:get"),
  /** Signal that listeners are registered, so buffered states are replayed. */
  notifyStartupReady: () => ipcRenderer.send("umi:startup-ready"),
});