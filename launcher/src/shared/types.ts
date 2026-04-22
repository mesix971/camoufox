// Types mirroring the Python bridge JSON schema (launcher/bridge/commands.py).
// Kept conservative — fields the renderer actually displays are typed,
// everything else is `unknown` to avoid drift if the bridge grows fields.

export interface ProfileSummary {
  id: string;
  name: string;
  archetype_id: string;
  os: string;
  locale: string;
  tags: string[];
  last_used_at: string | null;
  created_at: string;
  use_count: number;
  proxy_id: string | null;
}

export interface Profile extends ProfileSummary {
  firefox_version: string;
  user_agent: string;
  webgl_vendor: string;
  webgl_renderer: string;
  screen_width: number;
  screen_height: number;
  device_pixel_ratio: number;
  outer_width: number;
  outer_height: number;
  timezone: string;
  latitude: number;
  longitude: number;
  fonts: string[];
  cpu_cores: number;
  [k: string]: unknown;
}

export interface ProxySummary {
  id: string;
  label: string;
  provider: string;
  scheme: string;
  host: string;
  port: number;
  status: "untested" | "active" | "flagged" | "dead";
  country: string | null;
  observed_country: string | null;
  latency_ms: number | null;
  tags: string[];
  last_used_at: string | null;
  last_checked_at: string | null;
  use_count: number;
}

export interface Proxy extends ProxySummary {
  username: string | null;
  password: string | null;
  city: string | null;
  observed_ip: string | null;
  observed_city: string | null;
  sticky_session_id: string | null;
  sticky_session_lifetime: string | null;
  success_count: number;
  fail_count: number;
  consecutive_failures: number;
  total_checks: number;
  notes: string;
  [k: string]: unknown;
}

export interface Session {
  id: string;
  pid: number;
  profile_id: string;
  proxy_id: string | null;
  url: string | null;
  headless: boolean;
  log_path: string;
  started_at: string;
  stopped_at: string | null;
  status: "starting" | "running" | "stopped" | "crashed";
  exit_code: number | null;
  error: string | null;
}

export interface Archetype {
  id: string;
  os: string;
  os_version: string;
  weight: number;
  font_set_id: string;
  gpu_tier: string;
}

export interface HealthResult {
  proxy_id: string;
  ok: boolean;
  latency_ms: number | null;
  ip: string | null;
  country: string | null;
  city: string | null;
  error: string | null;
}

export interface ImportResult {
  parsed: number;
  saved: number;
  duplicates: number;
  errors: Array<{ line: number; raw: string; error: string }>;
}

export interface BridgeError {
  error: {
    type: string;
    message: string;
    traceback?: string;
  };
}

// IPC channel names — source of truth for main <-> preload <-> renderer.
export const IPC = {
  listProfiles: "list-profiles",
  showProfile: "show-profile",
  newProfile: "new-profile",
  deleteProfile: "delete-profile",
  listArchetypes: "list-archetypes",

  listProxies: "list-proxies",
  showProxy: "show-proxy",
  addProxy: "add-proxy",
  importProxies: "import-proxies",
  deleteProxy: "delete-proxy",
  checkProxy: "check-proxy",
  checkProxiesAll: "check-proxies-all",
  rotateProxySession: "rotate-proxy-session",

  listSessions: "list-sessions",
  launchSession: "launch-session",
  killSession: "kill-session",
  sessionLog: "session-log",
  pruneSessions: "prune-sessions",
  batchLaunchSession: "batch-launch-session",

  bindProfileProxy: "bind-profile-proxy",
  dashboardSummary: "dashboard-summary",
} as const;

export interface DashboardSummary {
  profiles: {
    total: number;
    by_os: Record<string, number>;
    bound_to_proxy: number;
  };
  proxies: {
    total: number;
    by_status: Record<string, number>;
  };
  sessions: {
    total: number;
    by_status: Record<string, number>;
    running: number;
  };
}

export interface BatchLaunchResult {
  spawned: Session[];
  failures: Array<{ profile_id: string; error: string }>;
  count: number;
}

export type ProxyStrategy = "bound" | "round-robin" | "fixed" | "none";

export type IpcChannel = typeof IPC[keyof typeof IPC];
