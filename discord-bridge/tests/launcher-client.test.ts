// Integration test: spawn a real `python -m launcher.bridge list-profiles`
// against a tmp FPGEN_STORE. Verifies the subprocess round-trip works.

import { strict as assert } from "node:assert";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { after, before, test } from "node:test";
import { SubprocessLaunchClient } from "../src/launcher-client";
import type { BridgeConfig } from "../src/types";

const REPO_ROOT = resolve(import.meta.dirname, "..", "..");

let storeDir: string;

before(() => {
  storeDir = mkdtempSync(join(tmpdir(), "dbridge-test-"));
  process.env.FPGEN_STORE = join(storeDir, "fpgen");
  process.env.PROXYPOOL_STORE = join(storeDir, "proxypool");
  process.env.LAUNCHER_SESSIONS = join(storeDir, "sessions");
});

after(() => {
  rmSync(storeDir, { recursive: true, force: true });
});

function mkCfg(): BridgeConfig {
  return {
    discord: { token: "n/a" },
    python_root: REPO_ROOT,
    python_executable: "python3",
    rules: [],
  };
}

test("listProfiles on empty store returns []", async () => {
  const client = new SubprocessLaunchClient(mkCfg());
  const profiles = await client.listProfiles();
  assert.deepEqual(profiles, []);
});

test("pickProfile with profile_strategy=id returns given id", async () => {
  const client = new SubprocessLaunchClient(mkCfg());
  // @ts-expect-error — private, but we're testing the logic not the API.
  const picked = client.pickProfile(
    { type: "launch-session", profile_strategy: "id", profile_id: "abcdef" },
    [],
  );
  assert.equal(picked, "abcdef");
});

test("pickProfile with tag=X returns null when no profile has that tag", async () => {
  const client = new SubprocessLaunchClient(mkCfg());
  // @ts-expect-error private
  const picked = client.pickProfile(
    { type: "launch-session", profile_strategy: "tag", profile_tag: "nonexistent" },
    [{ id: "a", os: "windows", tags: ["foo"], proxy_id: null, last_used_at: null, use_count: 0 }],
  );
  assert.equal(picked, null);
});

test("pickProfile LRU-sorts when multiple match", async () => {
  const client = new SubprocessLaunchClient(mkCfg());
  // @ts-expect-error private
  const picked = client.pickProfile(
    { type: "launch-session", profile_strategy: "tag", profile_tag: "T" },
    [
      { id: "old", os: "w", tags: ["T"], proxy_id: null, last_used_at: "2024-01-01T00:00:00+00:00", use_count: 5 },
      { id: "never", os: "w", tags: ["T"], proxy_id: null, last_used_at: null, use_count: 0 },
      { id: "recent", os: "w", tags: ["T"], proxy_id: null, last_used_at: "2025-10-01T00:00:00+00:00", use_count: 1 },
    ],
  );
  assert.equal(picked, "never"); // null last_used_at sorts before any string
});

test("pickProfile cycles round-robin across repeated picks", async () => {
  const client = new SubprocessLaunchClient(mkCfg());
  const profiles = [
    { id: "A", os: "w", tags: ["T"], proxy_id: null, last_used_at: null, use_count: 0 },
    { id: "B", os: "w", tags: ["T"], proxy_id: null, last_used_at: null, use_count: 0 },
    { id: "C", os: "w", tags: ["T"], proxy_id: null, last_used_at: null, use_count: 0 },
  ];
  const picks = Array.from({ length: 6 }, () => {
    // @ts-expect-error private
    return client.pickProfile(
      { type: "launch-session", profile_strategy: "tag", profile_tag: "T" },
      profiles,
    );
  });
  // Round-robin through sorted pool: A, B, C, A, B, C
  assert.deepEqual(picks, ["A", "B", "C", "A", "B", "C"]);
});
