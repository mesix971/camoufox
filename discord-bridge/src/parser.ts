// Rule matcher. Pure function for testability: takes a ParsedMessage plus
// a rule list and returns 0 or more matches.

import type { MatchResult, ParsedMessage, Rule } from "./types.js";

const URL_RE = /https?:\/\/[^\s<>"'`]+/g;

/**
 * Extract every URL from a message body. Used as the fallback when a rule's
 * regex has no capture group but we still need a URL to pass to the
 * launcher.
 */
export function extractUrls(content: string): string[] {
  return Array.from(content.matchAll(URL_RE), (m) => m[0]);
}

export function parseMessage(msg: {
  channelId: string;
  channelName: string;
  author: string;
  content: string;
  messageId: string;
}): ParsedMessage {
  return { ...msg, urls: extractUrls(msg.content) };
}

function channelMatches(rule: Rule, msg: ParsedMessage): boolean {
  if (!rule.match.channel) return true;
  const ch = rule.match.channel.toLowerCase();
  return (
    msg.channelId === rule.match.channel ||
    msg.channelName.toLowerCase() === ch
  );
}

function authorMatches(rule: Rule, msg: ParsedMessage): boolean {
  if (!rule.match.author) return true;
  return msg.author.toLowerCase() === rule.match.author.toLowerCase();
}

function contentMatchesAndExtractUrl(rule: Rule, msg: ParsedMessage): string | null {
  if (!rule.match.content_regex) {
    // No regex => match anything with at least one URL.
    return msg.urls[0] ?? null;
  }
  const rx = new RegExp(rule.match.content_regex, "i");
  const m = rx.exec(msg.content);
  if (!m) return null;
  if (rule.match.url_capture_group != null) {
    return m[rule.match.url_capture_group] ?? null;
  }
  // If the regex already matches a URL, return it.
  if (/^https?:\/\//i.test(m[0])) return m[0];
  // Otherwise use the first URL in the message, if any.
  return msg.urls[0] ?? null;
}

export function matchRules(msg: ParsedMessage, rules: Rule[]): MatchResult[] {
  const out: MatchResult[] = [];
  for (const rule of rules) {
    if (!channelMatches(rule, msg)) continue;
    if (!authorMatches(rule, msg)) continue;
    const url = contentMatchesAndExtractUrl(rule, msg);
    if (!url) continue;
    out.push({ rule, url, message: msg });
  }
  return out;
}
