// discord.js wrapper. Thin: connect, filter to configured channels, emit
// ParsedMessage for each message event.

import { Client, Events, GatewayIntentBits, type Message } from "discord.js";
import { log } from "./logger.js";
import { parseMessage } from "./parser.js";
import type { BridgeConfig, ParsedMessage } from "./types.js";

export type MessageHandler = (msg: ParsedMessage) => Promise<void> | void;

export class DiscordBridgeClient {
  private client: Client;

  constructor(
    private readonly cfg: BridgeConfig,
    private readonly onMessage: MessageHandler,
  ) {
    this.client = new Client({
      intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
      ],
    });

    this.client.once(Events.ClientReady, (c) => {
      log.info("discord ready", { tag: c.user.tag, guilds: c.guilds.cache.size });
    });

    this.client.on(Events.MessageCreate, (m) => void this.handle(m));
    this.client.on("error", (e) => log.error("discord client error", { err: e.message }));
  }

  async start(): Promise<void> {
    await this.client.login(this.cfg.discord.token);
  }

  async stop(): Promise<void> {
    await this.client.destroy();
  }

  private async handle(m: Message): Promise<void> {
    if (m.author.bot && !this.cfg.rules.some((r) => !!r.match.author && r.match.author.toLowerCase() === m.author.username.toLowerCase())) {
      // Ignore bot messages unless a rule explicitly targets one.
      return;
    }
    const channels = this.cfg.discord.channels;
    if (channels && channels.length > 0 && !channels.includes(m.channelId)) {
      return;
    }
    const channelName = "name" in m.channel && typeof m.channel.name === "string"
      ? m.channel.name : "";
    const parsed = parseMessage({
      channelId: m.channelId,
      channelName,
      author: m.author.username,
      content: m.content,
      messageId: m.id,
    });
    try {
      await this.onMessage(parsed);
    } catch (e) {
      log.error("handler threw", { err: (e as Error).message, messageId: m.id });
    }
  }
}
