// Tiny pino-style structured logger without a dep.

type Level = "debug" | "info" | "warn" | "error";

const LEVELS: Record<Level, number> = { debug: 10, info: 20, warn: 30, error: 40 };

function currentLevel(): Level {
  const v = (process.env.LOG_LEVEL || "info").toLowerCase();
  return (v in LEVELS ? v : "info") as Level;
}

const minLevel = LEVELS[currentLevel()];

function emit(level: Level, msg: string, extra?: unknown): void {
  if (LEVELS[level] < minLevel) return;
  const line = {
    t: new Date().toISOString(),
    level,
    msg,
    ...(extra && typeof extra === "object" ? (extra as Record<string, unknown>) : {}),
  };
  const stream = level === "error" || level === "warn" ? process.stderr : process.stdout;
  stream.write(JSON.stringify(line) + "\n");
}

export const log = {
  debug: (msg: string, extra?: unknown) => emit("debug", msg, extra),
  info: (msg: string, extra?: unknown) => emit("info", msg, extra),
  warn: (msg: string, extra?: unknown) => emit("warn", msg, extra),
  error: (msg: string, extra?: unknown) => emit("error", msg, extra),
};
