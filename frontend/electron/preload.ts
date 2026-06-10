import { contextBridge, ipcRenderer } from "electron";

// Expose a minimal, safe API surface to the renderer.
contextBridge.exposeInMainWorld("electronAPI", {
  platform: process.platform,
  versions: process.versions,
  send: (channel: string, data?: unknown) => ipcRenderer.send(channel, data),
});
