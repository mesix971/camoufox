import { strict as assert } from "node:assert";
import { test } from "node:test";
import { extractUrls, matchRules, parseMessage } from "../src/parser";
import type { Rule } from "../src/types";

const mkMsg = (content: string, channelName = "general", author = "user1") =>
  parseMessage({
    channelId: "100",
    channelName,
    author,
    content,
    messageId: "msg-1",
  });

const mkRule = (rule: Partial<Rule> & Pick<Rule, "name" | "match" | "action">): Rule => ({
  name: rule.name,
  match: rule.match,
  action: rule.action,
});

const launchAction = {
  type: "launch-session" as const,
  profile_strategy: "tag" as const,
  profile_tag: "ticketmaster",
};

test("extractUrls grabs every http(s) url", () => {
  const urls = extractUrls("hello https://a.com and http://b.example/path?x=1 done");
  assert.deepEqual(urls, ["https://a.com", "http://b.example/path?x=1"]);
});

test("extractUrls handles no url", () => {
  assert.deepEqual(extractUrls("no links here"), []);
});

test("matchRules returns empty when no rule matches", () => {
  const msg = mkMsg("hello https://foo.com");
  const rules = [mkRule({
    name: "other",
    match: { content_regex: "ticketmaster" },
    action: launchAction,
  })];
  assert.deepEqual(matchRules(msg, rules), []);
});

test("matchRules extracts url from regex with capture group", () => {
  const msg = mkMsg("bypass https://ticketmaster.fr/xyz now", "drops", "adonis");
  const rules = [mkRule({
    name: "adonis-bypass",
    match: {
      author: "adonis",
      content_regex: "bypass\\s+(https?://\\S+)",
      url_capture_group: 1,
    },
    action: launchAction,
  })];
  const result = matchRules(msg, rules);
  assert.equal(result.length, 1);
  assert.equal(result[0].url, "https://ticketmaster.fr/xyz");
});

test("matchRules filters by channel name (case-insensitive)", () => {
  const msg = mkMsg("https://a.com", "DROPS");
  const rules = [mkRule({
    name: "drops-only",
    match: { channel: "drops" },
    action: launchAction,
  })];
  assert.equal(matchRules(msg, rules).length, 1);
});

test("matchRules filters by channel id", () => {
  const msg = parseMessage({
    channelId: "abc-123",
    channelName: "other",
    author: "u",
    content: "https://a.com",
    messageId: "m",
  });
  const rules = [mkRule({
    name: "by-id",
    match: { channel: "abc-123" },
    action: launchAction,
  })];
  assert.equal(matchRules(msg, rules).length, 1);
});

test("matchRules author filter excludes mismatching authors", () => {
  const msg = mkMsg("https://a.com", "general", "alice");
  const rules = [mkRule({
    name: "bob-only",
    match: { author: "bob" },
    action: launchAction,
  })];
  assert.equal(matchRules(msg, rules).length, 0);
});

test("matchRules returns first URL when regex is content-only", () => {
  const msg = mkMsg("drop https://ticketmaster.fr/abc now!");
  const rules = [mkRule({
    name: "tm",
    match: { content_regex: "ticketmaster" },
    action: launchAction,
  })];
  const res = matchRules(msg, rules);
  assert.equal(res.length, 1);
  assert.equal(res[0].url, "https://ticketmaster.fr/abc");
});

test("matchRules yields 0 results when content regex matches but no URL present", () => {
  const msg = mkMsg("mentions ticketmaster but no url");
  const rules = [mkRule({
    name: "tm",
    match: { content_regex: "ticketmaster" },
    action: launchAction,
  })];
  assert.equal(matchRules(msg, rules).length, 0);
});

test("multiple rules can all match the same message", () => {
  const msg = mkMsg("drop https://ticketmaster.fr/x", "drops");
  const rules = [
    mkRule({ name: "tm-regex", match: { content_regex: "ticketmaster" }, action: launchAction }),
    mkRule({ name: "drops-channel", match: { channel: "drops" }, action: launchAction }),
  ];
  assert.equal(matchRules(msg, rules).length, 2);
});
