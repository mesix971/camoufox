// Exposes a typed `window.api` to the renderer. No Node globals leak.

import { contextBridge, ipcRenderer } from "electron";
import { IPC, type IpcChannel } from "../shared/types";

type ApiResponse<T> = { ok: true; data: T } | { ok: false; error: string };

const invoke = <T>(channel: IpcChannel, args: unknown = {}): Promise<T> =>
  ipcRenderer.invoke(channel, args).then((res: ApiResponse<T>) => {
    if (!res.ok) {
      throw new Error(res.error);
    }
    return res.data;
  });

const api = {
  // profiles
  listProfiles: (args?: { os?: string; tag?: string }) =>
    invoke(IPC.listProfiles, args ?? {}),
  showProfile: (id: string) => invoke(IPC.showProfile, { id }),
  newProfile: (args: {
    os?: string; archetype?: string; locale?: string;
    name?: string; tags?: string[]; seed?: number;
  }) => invoke(IPC.newProfile, args),
  deleteProfile: (id: string) => invoke(IPC.deleteProfile, { id }),
  listArchetypes: () => invoke(IPC.listArchetypes),

  // proxies
  listProxies: (args?: {
    status?: string; provider?: string; tag?: string; country?: string;
  }) => invoke(IPC.listProxies, args ?? {}),
  showProxy: (id: string) => invoke(IPC.showProxy, { id }),
  addProxy: (args: { line: string; label?: string; tags?: string[]; allow_duplicate?: boolean }) =>
    invoke(IPC.addProxy, args),
  importProxies: (args: { text: string; tag?: string; label_prefix?: string; allow_duplicate?: boolean }) =>
    invoke(IPC.importProxies, args),
  deleteProxy: (id: string) => invoke(IPC.deleteProxy, { id }),
  checkProxy: (id: string) => invoke(IPC.checkProxy, { id }),
  checkProxiesAll: (args?: { workers?: number; geo?: boolean }) =>
    invoke(IPC.checkProxiesAll, args ?? {}),
  rotateProxySession: (args: {
    id: string; session_id?: string; lifetime?: string;
    country?: string; city?: string; save_as_new?: boolean;
  }) => invoke(IPC.rotateProxySession, args),

  // sessions
  listSessions: () => invoke(IPC.listSessions),
  launchSession: (args: {
    profile_id: string; proxy_id?: string; url?: string; headless?: boolean;
  }) => invoke(IPC.launchSession, args),
  killSession: (id: string) => invoke(IPC.killSession, { id }),
  sessionLog: (id: string, lines = 200) => invoke(IPC.sessionLog, { id, lines }),
  pruneSessions: () => invoke(IPC.pruneSessions),
};

contextBridge.exposeInMainWorld("api", api);

export type Api = typeof api;
