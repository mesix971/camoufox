import { useEffect, useMemo, useRef, useState } from "react";
import {
  Search, CornerDownLeft, ArrowUp, ArrowDown, X,
  LayoutDashboard, Users, Globe, Monitor, ListChecks, Wand2, Settings,
  Palette, PanelTop, PanelLeft, Sparkles, Zap, RefreshCw, Webhook,
  type LucideIcon,
} from "lucide-react";
import { useAppStore, type AppState } from "../store";
import { THEMES, type LayoutId, type ThemeId } from "../themes";

/**
 * ⌘K / Ctrl+K command palette.
 *
 * Lists:
 *   - Tab navigation (7 tabs).
 *   - Theme switching (4 themes).
 *   - Layout switching (top vs sidebar).
 *   - Quick actions (refresh stores, new session, etc.).
 *
 * Open state lives in the store so any component can request it. Closes
 * on Escape, click outside, or after a command runs. Keyboard nav with
 * ↑↓; Enter to run the highlighted command.
 *
 * Search is a tiny score-based matcher — substrings score higher when
 * they hit the start of a word. Good enough for ~30 entries; no
 * dependency added.
 */
interface Command {
  id: string;
  label: string;
  section: string;
  icon: LucideIcon;
  // Optional aliases that still resolve to this command in search.
  keywords?: string[];
  // Hint shown on the right (e.g. current value indicator).
  hint?: string;
  run: (state: AppState) => void;
}

export function CommandPalette() {
  const open = useAppStore((s) => s.commandPaletteOpen);
  const close = useAppStore((s) => s.closeCommandPalette);
  const [query, setQuery] = useState("");
  const [highlightIndex, setHighlightIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const commands = useCommands();
  const filtered = useMemo(() => filterCommands(commands, query), [commands, query]);

  // Focus the input on open; reset state on close.
  useEffect(() => {
    if (open) {
      setQuery("");
      setHighlightIndex(0);
      // Defer so the element exists when we try to focus.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Keyboard nav within the palette.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        close();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlightIndex((i) => Math.min(filtered.length - 1, i + 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlightIndex((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const cmd = filtered[highlightIndex];
        if (cmd) {
          runCommand(cmd);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, filtered, highlightIndex, close]);

  // Keep highlight visible.
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(
      `[data-cmd-idx="${highlightIndex}"]`,
    );
    el?.scrollIntoView({ block: "nearest" });
  }, [highlightIndex]);

  // Reset highlight when filter changes.
  useEffect(() => {
    setHighlightIndex(0);
  }, [query, filtered.length]);

  if (!open) return null;

  const runCommand = (cmd: Command) => {
    cmd.run(useAppStore.getState());
    close();
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center pt-[15vh] bg-black/60"
      onClick={close}
    >
      <div
        className="w-full max-w-xl bg-surface-800 border border-surface-700 rounded-lg shadow-2xl
                   flex flex-col overflow-hidden command-palette"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-3 py-2.5 border-b border-surface-700">
          <Search size={16} className="text-surface-100/40 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            placeholder="Tapez une commande ou recherchez…"
            className="flex-1 bg-transparent outline-none text-sm placeholder-surface-100/30"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            type="button"
            onClick={close}
            className="text-surface-100/40 hover:text-surface-100/80 transition-colors"
            aria-label="Fermer"
          >
            <X size={14} />
          </button>
        </div>

        <div ref={listRef} className="max-h-[50vh] overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <div className="px-4 py-8 text-center text-surface-100/40 text-sm">
              Aucune commande pour « {query} »
            </div>
          ) : (
            renderGrouped(filtered, highlightIndex, runCommand)
          )}
        </div>

        <div className="flex items-center justify-between px-3 py-2 border-t border-surface-700
                        text-xs text-surface-100/40">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <ArrowUp size={11} />
              <ArrowDown size={11} />
              naviguer
            </span>
            <span className="flex items-center gap-1">
              <CornerDownLeft size={11} />
              valider
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 rounded border border-surface-700 bg-surface-900 font-mono text-[10px]">
                Esc
              </kbd>
              fermer
            </span>
          </div>
          <span>{filtered.length} commande{filtered.length > 1 ? "s" : ""}</span>
        </div>
      </div>
    </div>
  );
}

/* ---------- rendering ---------- */

function renderGrouped(
  items: Command[],
  highlightIndex: number,
  run: (cmd: Command) => void,
) {
  const groups = new Map<string, { cmd: Command; absoluteIndex: number }[]>();
  items.forEach((cmd, absoluteIndex) => {
    const arr = groups.get(cmd.section) ?? [];
    arr.push({ cmd, absoluteIndex });
    groups.set(cmd.section, arr);
  });
  const out: React.ReactNode[] = [];
  groups.forEach((entries, section) => {
    out.push(
      <div
        key={`h-${section}`}
        className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider text-surface-100/40 font-medium"
      >
        {section}
      </div>,
    );
    entries.forEach(({ cmd, absoluteIndex }) => {
      const Icon = cmd.icon;
      const active = absoluteIndex === highlightIndex;
      out.push(
        <button
          key={cmd.id}
          data-cmd-idx={absoluteIndex}
          type="button"
          onMouseEnter={() => {
            // Hover-to-highlight mirrors typical palettes.
            const el = document.querySelector<HTMLElement>(
              `[data-cmd-idx="${absoluteIndex}"]`,
            );
            el?.focus();
          }}
          onClick={() => run(cmd)}
          className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left transition-colors ${
            active
              ? "bg-accent-500/15 text-surface-100"
              : "text-surface-100/80 hover:bg-surface-700/50"
          }`}
        >
          <span className={`inline-flex items-center justify-center w-6 h-6 rounded-md ${
            active ? "bg-accent-500/25 text-accent-500" : "bg-surface-900 text-surface-100/70"
          }`}>
            <Icon size={13} strokeWidth={2.2} />
          </span>
          <span className="flex-1">{cmd.label}</span>
          {cmd.hint && (
            <span className="text-xs text-surface-100/40">{cmd.hint}</span>
          )}
          {active && (
            <CornerDownLeft size={12} className="text-surface-100/40" />
          )}
        </button>,
      );
    });
  });
  return out;
}

/* ---------- command catalog ---------- */

function useCommands(): Command[] {
  const currentTheme = useAppStore((s) => s.theme);
  const currentLayout = useAppStore((s) => s.layout);

  return useMemo<Command[]>(() => {
    const tabs: { id: AppState["tab"]; label: string; icon: LucideIcon }[] = [
      { id: "dashboard", label: "Aller au tableau de bord", icon: LayoutDashboard },
      { id: "profiles",  label: "Aller aux profils",        icon: Users },
      { id: "proxies",   label: "Aller aux proxies",        icon: Globe },
      { id: "sessions",  label: "Aller aux sessions",       icon: Monitor },
      { id: "tasks",     label: "Aller aux tâches",         icon: ListChecks },
      { id: "macros",    label: "Aller aux macros",         icon: Wand2 },
      { id: "settings",  label: "Ouvrir les paramètres",    icon: Settings },
    ];

    const navCommands: Command[] = tabs.map((t) => ({
      id: `nav.${t.id}`,
      label: t.label,
      section: "Navigation",
      icon: t.icon,
      keywords: [t.id],
      run: (state) => state.setTab(t.id),
    }));

    const themeCommands: Command[] = THEMES.map((t) => ({
      id: `theme.${t.id}`,
      label: `Thème — ${t.name}`,
      section: "Apparence",
      icon: Palette,
      keywords: ["theme", t.id, t.name.toLowerCase()],
      hint: currentTheme === t.id ? "actif" : undefined,
      run: (state) => state.setTheme(t.id as ThemeId),
    }));

    const layoutCommands: Command[] = [
      { id: "topbar"  as LayoutId, label: "Disposition — Barre supérieure", icon: PanelTop },
      { id: "sidebar" as LayoutId, label: "Disposition — Barre latérale",   icon: PanelLeft },
    ].map(({ id, label, icon }) => ({
      id: `layout.${id}`,
      label,
      section: "Apparence",
      icon,
      keywords: ["layout", "disposition", id],
      hint: currentLayout === id ? "actif" : undefined,
      run: (state) => state.setLayout(id),
    }));

    const quickActions: Command[] = [
      {
        id: "action.new-session",
        label: "Lancer une nouvelle session",
        section: "Actions",
        icon: Zap,
        keywords: ["nouveau", "session", "lancer", "start"],
        run: (state) => state.setTab("sessions"),
      },
      {
        id: "action.refresh-all",
        label: "Rafraîchir toutes les listes",
        section: "Actions",
        icon: RefreshCw,
        keywords: ["reload", "refresh", "actualiser"],
        run: (state) => {
          state.refreshProfiles();
          state.refreshProxies();
          state.refreshSessions();
          state.refreshTasks();
          state.refreshMacros();
        },
      },
      {
        id: "action.refresh-sessions",
        label: "Rafraîchir les sessions",
        section: "Actions",
        icon: RefreshCw,
        keywords: ["sessions"],
        run: (state) => state.refreshSessions({ metrics: true }),
      },
      {
        id: "action.go-webhook",
        label: "Configurer le webhook Discord",
        section: "Actions",
        icon: Webhook,
        keywords: ["webhook", "discord", "notif"],
        run: (state) => state.setTab("settings"),
      },
      {
        id: "action.go-appearance",
        label: "Modifier l'apparence",
        section: "Actions",
        icon: Sparkles,
        keywords: ["theme", "apparence", "appearance"],
        run: (state) => state.setTab("settings"),
      },
    ];

    return [...navCommands, ...themeCommands, ...layoutCommands, ...quickActions];
  }, [currentTheme, currentLayout]);
}

/* ---------- fuzzy filter ---------- */

function filterCommands(commands: Command[], query: string): Command[] {
  const q = query.trim().toLowerCase();
  if (!q) return commands;

  const scored = commands
    .map((cmd) => ({ cmd, score: scoreCommand(cmd, q) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score);
  return scored.map((s) => s.cmd);
}

function scoreCommand(cmd: Command, query: string): number {
  const haystacks: { text: string; weight: number }[] = [
    { text: cmd.label.toLowerCase(),   weight: 1.0 },
    { text: cmd.section.toLowerCase(), weight: 0.4 },
    ...(cmd.keywords ?? []).map((k) => ({ text: k.toLowerCase(), weight: 0.7 })),
  ];
  let best = 0;
  for (const { text, weight } of haystacks) {
    const idx = text.indexOf(query);
    if (idx < 0) continue;
    // Prefix match scores best, mid-word match counts but lower.
    const positional = idx === 0 ? 1 : isWordStart(text, idx) ? 0.7 : 0.4;
    const ratio = query.length / text.length; // longer query / shorter haystack = better
    const s = weight * positional * (0.5 + 0.5 * ratio);
    if (s > best) best = s;
  }
  return best;
}

function isWordStart(s: string, idx: number): boolean {
  if (idx === 0) return true;
  const c = s.charAt(idx - 1);
  return c === " " || c === "-" || c === "_" || c === ".";
}
