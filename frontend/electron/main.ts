import { app, BrowserWindow, session, shell } from "electron";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirnameResolved = path.dirname(fileURLToPath(import.meta.url));

// Vite injects these env vars during development.
const VITE_DEV_SERVER_URL = process.env["VITE_DEV_SERVER_URL"];
const DIST = path.join(__dirnameResolved, "../dist");

let mainWindow: BrowserWindow | null = null;

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: "#0b0f17",
    title: "Cache AI Assistant",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirnameResolved, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Open external links in the system browser.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  if (VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(VITE_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(path.join(DIST, "index.html"));
  }
}

app.whenReady().then(() => {
  // Allow microphone access for voice input in the Electron shell.
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    const allowed = new Set(["media", "audioCapture", "microphone"]);
    callback(allowed.has(permission));
  });
  session.defaultSession.setPermissionCheckHandler((_wc, permission) => {
    const allowed = new Set(["media", "audioCapture", "microphone"]);
    return allowed.has(permission);
  });
  createWindow();
});

app.on("window-all-closed", () => {
  mainWindow = null;
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
