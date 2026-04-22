// Electron app entry.

import { app, BrowserWindow } from "electron";
import { registerIpcHandlers } from "./ipc";
import { createMainWindow } from "./window";

function bootstrap(): void {
  registerIpcHandlers();
  createMainWindow();
}

app.whenReady().then(bootstrap);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createMainWindow();
  }
});
