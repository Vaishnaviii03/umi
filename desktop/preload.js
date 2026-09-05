"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("umi", {
  platform: process.platform,
  onStartupState: (callback) =>
    ipcRenderer.on("umi:startup-state", (_event, payload) => callback(payload)),
});