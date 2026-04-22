// IPC handler registration.
// Every channel maps 1:1 to a Python bridge command. The renderer calls them
// via window.api.* (see preload).

import { ipcMain } from "electron";
import { IPC, type IpcChannel } from "../shared/types";
import { callBridge } from "./bridge";

type Handler = (args: Record<string, unknown>) => Promise<unknown>;

/**
 * Register all IPC handlers. Each handler just forwards to the bridge.
 * Special case: `import-proxies` receives the blob text in args.text, which
 * is large — still forwarded as a JSON arg (not via stdin) since the bridge
 * accepts it inline and the blob sizes we care about (<1MB) comfortably fit.
 */
export function registerIpcHandlers(): void {
  const channels: IpcChannel[] = Object.values(IPC);
  for (const channel of channels) {
    const handler: Handler = (args) => callBridge(channel, args || {});
    ipcMain.handle(channel, async (_event, args: Record<string, unknown>) => {
      try {
        return { ok: true, data: await handler(args) };
      } catch (err) {
        return { ok: false, error: (err as Error).message };
      }
    });
  }
}
