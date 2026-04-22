// Config loader: read JSON from disk, expand ${ENV_VAR} refs, validate shape.

import { readFileSync } from "node:fs";
import type { BridgeConfig, Rule } from "./types.js";

const ENV_REF = /^\$\{([A-Z0-9_]+)\}$/;

export class ConfigError extends Error {
  constructor(msg: string) {
    super(msg);
    this.name = "ConfigError";
  }
}

function expandEnv(value: string): string {
  const m = ENV_REF.exec(value);
  if (!m) return value;
  const v = process.env[m[1]];
  if (!v) throw new ConfigError(`env var ${m[1]} referenced in config is not set`);
  return v;
}

export function loadConfig(path: string): BridgeConfig {
  const raw = readFileSync(path, "utf8");
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    throw new ConfigError(`config file ${path} is not valid JSON: ${(e as Error).message}`);
  }
  return validate(parsed);
}

export function validate(raw: unknown): BridgeConfig {
  if (!raw || typeof raw !== "object") {
    throw new ConfigError("config must be an object");
  }
  const cfg = raw as Partial<BridgeConfig>;

  if (!cfg.discord || typeof cfg.discord !== "object") {
    throw new ConfigError("missing `discord` block");
  }
  if (!cfg.discord.token || typeof cfg.discord.token !== "string") {
    throw new ConfigError("missing `discord.token`");
  }
  cfg.discord.token = expandEnv(cfg.discord.token);

  if (cfg.discord.channels && !Array.isArray(cfg.discord.channels)) {
    throw new ConfigError("`discord.channels` must be an array of strings");
  }

  if (!cfg.python_root || typeof cfg.python_root !== "string") {
    throw new ConfigError("missing `python_root` (path to the camoufox repo)");
  }

  if (!Array.isArray(cfg.rules)) {
    throw new ConfigError("`rules` must be an array");
  }
  cfg.rules.forEach((r, i) => validateRule(r, i));

  return cfg as BridgeConfig;
}

function validateRule(rule: unknown, index: number): void {
  if (!rule || typeof rule !== "object") {
    throw new ConfigError(`rules[${index}] must be an object`);
  }
  const r = rule as Partial<Rule>;
  if (!r.name || typeof r.name !== "string") {
    throw new ConfigError(`rules[${index}].name is required`);
  }
  if (!r.match || typeof r.match !== "object") {
    throw new ConfigError(`rules[${index}].match is required`);
  }
  if (r.match.content_regex) {
    try { new RegExp(r.match.content_regex); }
    catch { throw new ConfigError(`rules[${index}].match.content_regex is not a valid regex`); }
  }
  if (!r.action || typeof r.action !== "object") {
    throw new ConfigError(`rules[${index}].action is required`);
  }
  if (r.action.type !== "launch-session") {
    throw new ConfigError(`rules[${index}].action.type must be 'launch-session'`);
  }
  const strategies = ["tag", "os", "id", "any"];
  if (!strategies.includes(r.action.profile_strategy)) {
    throw new ConfigError(
      `rules[${index}].action.profile_strategy must be one of ${strategies.join("|")}`,
    );
  }
  if (r.action.profile_strategy === "tag" && !r.action.profile_tag) {
    throw new ConfigError(`rules[${index}].action.profile_tag required when strategy=tag`);
  }
  if (r.action.profile_strategy === "id" && !r.action.profile_id) {
    throw new ConfigError(`rules[${index}].action.profile_id required when strategy=id`);
  }
}
