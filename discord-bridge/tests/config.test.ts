import { strict as assert } from "node:assert";
import { test } from "node:test";
import { ConfigError, validate } from "../src/config";

const baseValid = () => ({
  discord: { token: "abc", channels: ["123"] },
  python_root: "/tmp/camoufox",
  rules: [
    {
      name: "r1",
      match: { content_regex: "https://.*" },
      action: { type: "launch-session", profile_strategy: "any" },
    },
  ],
});

test("validate accepts minimal config", () => {
  const cfg = validate(baseValid());
  assert.equal(cfg.discord.token, "abc");
  assert.equal(cfg.rules.length, 1);
});

test("expands ${ENV_VAR} in token", () => {
  process.env.TEST_DISCORD_TOKEN = "real-token-xyz";
  const raw = baseValid();
  raw.discord.token = "${TEST_DISCORD_TOKEN}";
  const cfg = validate(raw);
  assert.equal(cfg.discord.token, "real-token-xyz");
  delete process.env.TEST_DISCORD_TOKEN;
});

test("throws if referenced env var is missing", () => {
  const raw = baseValid();
  raw.discord.token = "${NOT_SET_XYZ}";
  assert.throws(() => validate(raw), ConfigError);
});

test("rejects missing python_root", () => {
  const raw: Record<string, unknown> = baseValid();
  delete raw.python_root;
  assert.throws(() => validate(raw), /python_root/);
});

test("rejects bad regex in rule", () => {
  const raw = baseValid();
  raw.rules[0].match = { content_regex: "[unterminated" };
  assert.throws(() => validate(raw), /content_regex/);
});

test("rejects unknown profile_strategy", () => {
  const raw = baseValid();
  (raw.rules[0].action as Record<string, unknown>).profile_strategy = "magic";
  assert.throws(() => validate(raw), /profile_strategy/);
});

test("requires profile_tag when strategy=tag", () => {
  const raw = baseValid();
  raw.rules[0].action.profile_strategy = "tag";
  assert.throws(() => validate(raw), /profile_tag/);
});

test("requires profile_id when strategy=id", () => {
  const raw = baseValid();
  raw.rules[0].action.profile_strategy = "id";
  assert.throws(() => validate(raw), /profile_id/);
});

test("rejects action.type that is not launch-session", () => {
  const raw = baseValid();
  raw.rules[0].action.type = "post-message";
  assert.throws(() => validate(raw), /launch-session/);
});

test("rejects non-array rules", () => {
  const raw: Record<string, unknown> = baseValid();
  raw.rules = "not an array";
  assert.throws(() => validate(raw), /rules/);
});
