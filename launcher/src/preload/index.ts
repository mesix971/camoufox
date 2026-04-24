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
  listSessions: (args?: { metrics?: boolean }) =>
    invoke(IPC.listSessions, args ?? {}),
  launchSession: (args: {
    profile_id: string; proxy_id?: string; url?: string; headless?: boolean;
    warmup?: boolean; auto_refresh?: number; persistent?: boolean;
    queue_monitor?: boolean; rate_limit?: number;
    humanlike?: boolean; run_macro?: string; record_macro?: string;
  }) => invoke(IPC.launchSession, args),
  killSession: (id: string) => invoke(IPC.killSession, { id }),
  reopenSession: (id: string, args?: { url?: string; headless?: boolean }) =>
    invoke(IPC.reopenSession, { id, ...(args ?? {}) }),
  sessionLog: (id: string, lines = 200) => invoke(IPC.sessionLog, { id, lines }),
  pruneSessions: () => invoke(IPC.pruneSessions),
  batchLaunchSession: (args: {
    profile_ids: string[];
    strategy: "bound" | "round-robin" | "fixed" | "none";
    proxy_id?: string;
    proxy_filter?: { provider?: string; country?: string; tag?: string; status?: string };
    url?: string;
    headless?: boolean;
    warmup?: boolean;
    auto_refresh?: number;
    persistent?: boolean;
    queue_monitor?: boolean;
    rate_limit?: number;
    humanlike?: boolean;
    run_macro?: string;
    tile?: boolean;
    grid?: string;  // 'auto' | 'CxR'
  }) => invoke(IPC.batchLaunchSession, args),
  sessionMetrics: () => invoke(IPC.sessionMetrics, {}),

  // binding + dashboard
  bindProfileProxy: (args: { profile_id: string; proxy_id: string | null }) =>
    invoke(IPC.bindProfileProxy, args),
  dashboardSummary: () => invoke(IPC.dashboardSummary),

  // profile clone/update/export/import
  cloneProfile: (args: { id: string; name?: string; tags?: string[] }) =>
    invoke(IPC.cloneProfile, args),
  updateProfile: (args: { id: string; updates: Record<string, unknown> }) =>
    invoke(IPC.updateProfile, args),
  exportProfile: (args: { id: string }) => invoke(IPC.exportProfile, args),
  importProfile: (args: { profile: Record<string, unknown>; rename?: boolean }) =>
    invoke(IPC.importProfile, args),

  // webhook
  setWebhook: (args: { url: string }) => invoke(IPC.setWebhook, args),
  getWebhook: () => invoke(IPC.getWebhook, {}),
  testWebhook: (args?: { content?: string; level?: string }) =>
    invoke(IPC.testWebhook, args ?? {}),

  // ratelimit
  ratelimitStats: (args?: { host?: string }) =>
    invoke(IPC.ratelimitStats, args ?? {}),
  ratelimitSet: (args: { host: string; max_per_minute: number }) =>
    invoke(IPC.ratelimitSet, args),

  // tasks
  enqueueTask: (args: {
    action: Record<string, unknown>;
    delay_seconds?: number;
    run_at?: string;
    tags?: string[];
  }) => invoke(IPC.enqueueTask, args),
  listTasks: (args?: { status?: string; tag?: string }) =>
    invoke(IPC.listTasks, args ?? {}),
  deleteTask: (args: { id: string }) => invoke(IPC.deleteTask, args),

  // CreepJS scoring
  scoreProfileCreepjs: (args: {
    profile_id: string;
    pass_fp_threshold?: number;
    pass_trust_threshold?: number;
    headless?: boolean;
    save_to_profile?: boolean;
  }) => invoke(IPC.scoreProfileCreepjs, args),

  // macros
  listMacros: () => invoke(IPC.listMacros, {}),
  showMacro: (args: { name: string }) => invoke(IPC.showMacro, args),
  saveMacro: (args: {
    name: string;
    actions: unknown[];
    metadata?: Record<string, unknown>;
  }) => invoke(IPC.saveMacro, args),
  deleteMacro: (args: { name: string }) => invoke(IPC.deleteMacro, args),
};

contextBridge.exposeInMainWorld("api", api);

export type Api = typeof api;
