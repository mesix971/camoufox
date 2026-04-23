// Global UI store. Keeps fetched lists + selection state + async status flags.

import { create } from "zustand";
import type {
  Archetype, CreepJSScore, Macro, ProfileSummary, ProxySummary,
  SessionWithMetrics, Task,
} from "../../shared/types";
import { api } from "../api";

export interface AppState {
  tab: "dashboard" | "profiles" | "proxies" | "sessions" | "tasks" | "macros" | "settings";
  setTab: (t: AppState["tab"]) => void;

  profiles: ProfileSummary[];
  profilesLoading: boolean;
  profilesError: string | null;
  refreshProfiles: () => Promise<void>;

  proxies: ProxySummary[];
  proxiesLoading: boolean;
  proxiesError: string | null;
  refreshProxies: () => Promise<void>;

  sessions: SessionWithMetrics[];
  sessionsLoading: boolean;
  sessionsError: string | null;
  psutilAvailable: boolean;
  refreshSessions: (opts?: { metrics?: boolean }) => Promise<void>;

  tasks: Task[];
  tasksStats: Record<string, number>;
  tasksLoading: boolean;
  tasksError: string | null;
  refreshTasks: () => Promise<void>;

  archetypes: Archetype[];
  loadArchetypes: () => Promise<void>;

  macros: Macro[];
  macrosLoading: boolean;
  macrosError: string | null;
  refreshMacros: () => Promise<void>;

  // Latest CreepJS score per profile_id (kept in memory only).
  creepjsScores: Record<string, CreepJSScore>;
  setCreepjsScore: (profileId: string, score: CreepJSScore) => void;

  // Global toast
  toast: { kind: "info" | "error" | "success"; text: string } | null;
  showToast: (kind: "info" | "error" | "success", text: string) => void;
  clearToast: () => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  tab: "dashboard",
  setTab: (tab) => set({ tab }),

  profiles: [],
  profilesLoading: false,
  profilesError: null,
  refreshProfiles: async () => {
    set({ profilesLoading: true, profilesError: null });
    try {
      const res = await api().listProfiles() as { profiles: ProfileSummary[] };
      set({ profiles: res.profiles, profilesLoading: false });
    } catch (e) {
      set({ profilesError: (e as Error).message, profilesLoading: false });
    }
  },

  proxies: [],
  proxiesLoading: false,
  proxiesError: null,
  refreshProxies: async () => {
    set({ proxiesLoading: true, proxiesError: null });
    try {
      const res = await api().listProxies() as { proxies: ProxySummary[] };
      set({ proxies: res.proxies, proxiesLoading: false });
    } catch (e) {
      set({ proxiesError: (e as Error).message, proxiesLoading: false });
    }
  },

  sessions: [],
  sessionsLoading: false,
  sessionsError: null,
  psutilAvailable: true,
  refreshSessions: async (opts) => {
    set({ sessionsLoading: true, sessionsError: null });
    try {
      const res = await api().listSessions(opts ?? {}) as {
        sessions: SessionWithMetrics[];
        psutil_available?: boolean;
      };
      set({
        sessions: res.sessions,
        sessionsLoading: false,
        psutilAvailable: res.psutil_available ?? true,
      });
    } catch (e) {
      set({ sessionsError: (e as Error).message, sessionsLoading: false });
    }
  },

  tasks: [],
  tasksStats: {},
  tasksLoading: false,
  tasksError: null,
  refreshTasks: async () => {
    set({ tasksLoading: true, tasksError: null });
    try {
      const res = await api().listTasks() as {
        tasks: Task[]; stats: Record<string, number>;
      };
      set({
        tasks: res.tasks,
        tasksStats: res.stats || {},
        tasksLoading: false,
      });
    } catch (e) {
      set({ tasksError: (e as Error).message, tasksLoading: false });
    }
  },

  archetypes: [],
  loadArchetypes: async () => {
    if (get().archetypes.length > 0) return;
    try {
      const res = await api().listArchetypes() as { archetypes: Archetype[] };
      set({ archetypes: res.archetypes });
    } catch (e) {
      set({ toast: { kind: "error", text: (e as Error).message } });
    }
  },

  macros: [],
  macrosLoading: false,
  macrosError: null,
  refreshMacros: async () => {
    set({ macrosLoading: true, macrosError: null });
    try {
      const res = await api().listMacros() as { macros: Macro[] };
      set({ macros: res.macros ?? [], macrosLoading: false });
    } catch (e) {
      set({ macrosError: (e as Error).message, macrosLoading: false });
    }
  },

  creepjsScores: {},
  setCreepjsScore: (profileId, score) =>
    set((s) => ({
      creepjsScores: { ...s.creepjsScores, [profileId]: score },
    })),

  toast: null,
  showToast: (kind, text) => {
    set({ toast: { kind, text } });
    setTimeout(() => {
      if (get().toast?.text === text) set({ toast: null });
    }, 4000);
  },
  clearToast: () => set({ toast: null }),
}));
