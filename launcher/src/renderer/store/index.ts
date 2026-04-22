// Global UI store. Keeps fetched lists + selection state + async status flags.

import { create } from "zustand";
import type {
  Archetype, ProfileSummary, ProxySummary, Session,
} from "../../shared/types";
import { api } from "../api";

export interface AppState {
  tab: "dashboard" | "profiles" | "proxies" | "sessions";
  setTab: (t: AppState["tab"]) => void;

  profiles: ProfileSummary[];
  profilesLoading: boolean;
  profilesError: string | null;
  refreshProfiles: () => Promise<void>;

  proxies: ProxySummary[];
  proxiesLoading: boolean;
  proxiesError: string | null;
  refreshProxies: () => Promise<void>;

  sessions: Session[];
  sessionsLoading: boolean;
  sessionsError: string | null;
  refreshSessions: () => Promise<void>;

  archetypes: Archetype[];
  loadArchetypes: () => Promise<void>;

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
  refreshSessions: async () => {
    set({ sessionsLoading: true, sessionsError: null });
    try {
      const res = await api().listSessions() as { sessions: Session[] };
      set({ sessions: res.sessions, sessionsLoading: false });
    } catch (e) {
      set({ sessionsError: (e as Error).message, sessionsLoading: false });
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

  toast: null,
  showToast: (kind, text) => {
    set({ toast: { kind, text } });
    setTimeout(() => {
      if (get().toast?.text === text) set({ toast: null });
    }, 4000);
  },
  clearToast: () => set({ toast: null }),
}));
