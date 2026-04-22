// Shared types for the discord-bridge.

export interface BridgeConfig {
  discord: {
    /** Bot token. Supports ${ENV_VAR} interpolation. */
    token: string;
    /** Channel IDs (string form, as Discord returns them). Empty = all channels. */
    channels?: string[];
  };

  /** Root of the Camoufox repo (contains fpgen/, proxypool/, launcher/). */
  python_root: string;
  /** Python executable (default: python3). */
  python_executable?: string;

  rules: Rule[];

  /** Dry run = parse + log matches but don't launch. */
  dry_run?: boolean;
}

export interface Rule {
  name: string;
  match: {
    /** Match the channel name or id. Case-insensitive for names. */
    channel?: string;
    /** Match author username / nickname. Case-insensitive. */
    author?: string;
    /** ECMAScript regex against message content. */
    content_regex?: string;
    /** Capture group index to extract as the URL (default: first full URL found). */
    url_capture_group?: number;
  };
  action: LaunchAction;
}

export interface LaunchAction {
  type: "launch-session";
  /** How to pick a profile:
   *  - 'tag'  : pick one (round-robin across runs) whose tags include profile_tag
   *  - 'os'   : pick one whose os matches profile_os
   *  - 'id'   : use profile_id verbatim
   *  - 'any'  : pick any profile (round-robin)
   */
  profile_strategy: "tag" | "os" | "id" | "any";
  profile_tag?: string;
  profile_os?: string;
  profile_id?: string;

  /** Proxy strategy (maps to bridge batch-launch-session strategies). */
  proxy_strategy?: "bound" | "round-robin" | "fixed" | "none";
  proxy_id?: string;

  /** Headless vs windowed. */
  headless?: boolean;
}

export interface ParsedMessage {
  channelId: string;
  channelName: string;
  author: string;
  content: string;
  messageId: string;
  urls: string[];
}

export interface MatchResult {
  rule: Rule;
  url: string;
  /** The parsed message that triggered this match. */
  message: ParsedMessage;
}

export interface ProfileSummary {
  id: string;
  os: string;
  tags: string[];
  proxy_id: string | null;
  last_used_at: string | null;
  use_count: number;
}
