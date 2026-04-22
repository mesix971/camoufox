// Entry point. Loads config, wires discord -> parser -> launcher.

import { DiscordBridgeClient } from "./discord-client.js";
import { loadConfig } from "./config.js";
import { SubprocessLaunchClient } from "./launcher-client.js";
import { log } from "./logger.js";
import { matchRules } from "./parser.js";

async function main(): Promise<void> {
  const configPath = process.argv[2] || process.env.BRIDGE_CONFIG || "config.json";
  const cfg = loadConfig(configPath);
  log.info("config loaded", {
    path: configPath,
    rules: cfg.rules.length,
    channels: cfg.discord.channels?.length ?? "all",
    dryRun: !!cfg.dry_run,
  });

  const launcher = new SubprocessLaunchClient(cfg);

  const client = new DiscordBridgeClient(cfg, async (msg) => {
    const matches = matchRules(msg, cfg.rules);
    if (matches.length === 0) return;
    log.info("matched", {
      messageId: msg.messageId,
      author: msg.author,
      channel: msg.channelName,
      hits: matches.map((m) => ({ rule: m.rule.name, url: m.url })),
    });
    for (const hit of matches) {
      if (cfg.dry_run) {
        log.info("dry run skipping launch", { rule: hit.rule.name, url: hit.url });
        continue;
      }
      try {
        const res = await launcher.launchSession(hit.rule.action, hit.url);
        log.info("launched", { rule: hit.rule.name, url: hit.url, session: res.session_id, pid: res.pid });
      } catch (e) {
        log.error("launch failed", { rule: hit.rule.name, url: hit.url, err: (e as Error).message });
      }
    }
  });

  await client.start();

  const shutdown = async () => {
    log.info("shutting down");
    await client.stop();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((e) => {
  log.error("fatal", { err: (e as Error).message, stack: (e as Error).stack });
  process.exit(1);
});
