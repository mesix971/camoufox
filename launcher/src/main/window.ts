// BrowserWindow factory.

import { BrowserWindow } from "electron";
import { join } from "node:path";

export function createMainWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 600,
    backgroundColor: "#0f0f0f",
    autoHideMenuBar: true,
    title: "Camoufox Launcher",
    webPreferences: {
      // __dirname at runtime = dist/main/main
      preload: join(__dirname, "..", "preload", "index.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false, // preload uses ipcRenderer via contextBridge
    },
  });

  // dist/main/main/../../renderer/index.html = dist/renderer/index.html
  win.loadFile(join(__dirname, "..", "..", "renderer", "index.html"));

  if (process.env.CAMOUFOX_LAUNCHER_DEVTOOLS === "1") {
    win.webContents.openDevTools({ mode: "detach" });
  }

  return win;
}
