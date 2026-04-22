// Calls the Camoufox Python launcher bridge as a subprocess and returns
// parsed JSON. Mirrors launcher/src/main/bridge.ts but sync-wrapped-async
// and without Electron imports.

import { spawn } from "node:child_process";
import type { BridgeConfig, LaunchAction, ProfileSummary } from "./types.js";

export interface LaunchClient {
  listProfiles(): Promise<ProfileSummary[]>;
  launchSession(action: LaunchAction, url: string): Promise<{ session_id: string; pid: number }>;
}

export class SubprocessLaunchClient implements LaunchClient {
  // Round-robin cursor per profile_strategy+tag so different rules don't
  // collide on the same counter.
  private cursors: Map<string, number> = new Map();

  constructor(private readonly cfg: BridgeConfig) {}

  async listProfiles(): Promise<ProfileSummary[]> {
    const res = await this.call<{ profiles: ProfileSummary[] }>("list-profiles", {});
    return res.profiles;
  }

  async launchSession(action: LaunchAction, url: string): Promise<{ session_id: string; pid: number }> {
    const profiles = await this.listProfiles();
    const profileId = this.pickProfile(action, profiles);
    if (!profileId) {
      throw new Error(`no profile matches action ${JSON.stringify(action)}`);
    }

    const args: Record<string, unknown> = {
      profile_id: profileId,
      url,
      headless: action.headless ?? false,
    };
    if (action.proxy_strategy === "fixed" && action.proxy_id) {
      args.proxy_id = action.proxy_id;
    }
    // For 'bound', the bridge's launch-session already picks the profile's
    // bound proxy implicitly if we omit proxy_id and profile.proxy_id is set.
    // But launch-session does NOT auto-bind — it only uses proxy_id when
    // explicitly passed. Read the profile and use its proxy_id.
    if (action.proxy_strategy === "bound") {
      const p = profiles.find((x) => x.id === profileId);
      if (p?.proxy_id) args.proxy_id = p.proxy_id;
    }

    const res = await this.call<{ session: { id: string; pid: number } }>("launch-session", args);
    return { session_id: res.session.id, pid: res.session.pid };
  }

  private pickProfile(action: LaunchAction, profiles: ProfileSummary[]): string | null {
    let pool: ProfileSummary[];
    let key: string;
    switch (action.profile_strategy) {
      case "id":
        return action.profile_id ?? null;
      case "tag":
        pool = profiles.filter((p) => p.tags.includes(action.profile_tag!));
        key = `tag:${action.profile_tag}`;
        break;
      case "os":
        pool = profiles.filter((p) => p.os === action.profile_os);
        key = `os:${action.profile_os}`;
        break;
      case "any":
      default:
        pool = profiles;
        key = "any";
    }
    if (pool.length === 0) return null;
    // Round-robin + prefer least-recently-used to spread load.
    pool.sort((a, b) => {
      const la = a.last_used_at || "";
      const lb = b.last_used_at || "";
      if (la !== lb) return la < lb ? -1 : 1;
      return a.use_count - b.use_count;
    });
    const cursor = this.cursors.get(key) ?? 0;
    this.cursors.set(key, cursor + 1);
    return pool[cursor % pool.length].id;
  }

  private call<T>(command: string, args: Record<string, unknown>): Promise<T> {
    const python = this.cfg.python_executable || "python3";
    const argv = ["-m", "launcher.bridge", command, JSON.stringify(args)];
    return new Promise<T>((resolve, reject) => {
      const child = spawn(python, argv, {
        cwd: this.cfg.python_root,
        env: {
          ...process.env,
          PYTHONPATH: `${this.cfg.python_root}${process.env.PYTHONPATH ? ":" + process.env.PYTHONPATH : ""}`,
        },
      });
      let stdout = "", stderr = "";
      child.stdout.on("data", (c) => (stdout += c.toString()));
      child.stderr.on("data", (c) => (stderr += c.toString()));
      child.on("error", (e) => reject(e));
      child.on("close", (code) => {
        let parsed: unknown;
        try { parsed = JSON.parse(stdout); }
        catch {
          reject(new Error(`bridge ${command} exit=${code} returned non-JSON:\n${stdout}\n---\n${stderr}`));
          return;
        }
        if (code === 0) { resolve(parsed as T); return; }
        const err = parsed as { error?: { message?: string } };
        reject(new Error(`bridge ${command} failed: ${err.error?.message || JSON.stringify(parsed)}`));
      });
    });
  }
}
