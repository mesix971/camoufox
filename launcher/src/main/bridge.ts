// Thin wrapper around the Python JSON bridge (launcher.bridge).
// Every invocation is one subprocess that prints exactly one JSON object
// on stdout and exits. Non-zero exit with error JSON = rejection.

import { spawn } from "node:child_process";
import { resolve } from "node:path";
import type { BridgeError, IpcChannel } from "../shared/types";

// At runtime: __dirname = launcher/dist/main/main
// Repo root (camoufox) = four levels up.
const REPO_ROOT = resolve(__dirname, "..", "..", "..", "..");
const PYTHON = process.env.CAMOUFOX_PYTHON || "python3";

export interface BridgeOptions {
  timeoutMs?: number;
  /** Extra text to feed on stdin (used by import-proxies for bulk paste). */
  stdin?: string;
}

/**
 * Invoke a bridge command. Returns the parsed JSON payload on success,
 * throws with a BridgeError-shaped message on failure.
 */
export async function callBridge<T = unknown>(
  channel: IpcChannel,
  args: Record<string, unknown> = {},
  options: BridgeOptions = {},
): Promise<T> {
  const timeout = options.timeoutMs ?? 60_000;
  const argv = [
    "-m", "launcher.bridge",
    channel,
    JSON.stringify(args),
  ];

  return new Promise<T>((resolvePromise, reject) => {
    const child = spawn(PYTHON, argv, {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        PYTHONPATH: `${REPO_ROOT}${process.env.PYTHONPATH ? ":" + process.env.PYTHONPATH : ""}`,
      },
    });

    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      reject(new Error(`bridge command ${channel} timed out after ${timeout}ms`));
    }, timeout);

    if (options.stdin !== undefined) {
      child.stdin.write(options.stdin);
      child.stdin.end();
    } else {
      child.stdin.end();
    }

    child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });

    child.on("error", (err) => {
      clearTimeout(timer);
      reject(new Error(`failed to spawn python: ${err.message}`));
    });

    child.on("close", (code) => {
      clearTimeout(timer);
      let parsed: unknown;
      try {
        parsed = JSON.parse(stdout);
      } catch {
        reject(new Error(
          `bridge ${channel} exit=${code} returned non-JSON:\nstdout: ${stdout}\nstderr: ${stderr}`,
        ));
        return;
      }
      if (code === 0) {
        resolvePromise(parsed as T);
        return;
      }
      const err = parsed as BridgeError;
      const detail = err.error?.message || JSON.stringify(parsed);
      reject(new Error(`bridge ${channel} failed: ${detail}`));
    });
  });
}
