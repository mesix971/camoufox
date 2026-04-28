// Theme catalogue + helpers used by the React store and Settings UI.
//
// Adding a new theme means: add a CSS block in themes.css, then add an
// entry here so the picker shows it.

export type ThemeId = "camoufox" | "linear" | "raycast" | "brutalist";

export interface ThemeDescriptor {
  id: ThemeId;
  name: string;
  description: string;
  // Three swatch colors used by the picker preview tile (bg, surface, accent).
  swatches: [string, string, string];
}

export const THEMES: ThemeDescriptor[] = [
  {
    id: "camoufox",
    name: "Camoufox",
    description: "Le thème d'origine — sombre neutre + accent violet.",
    swatches: ["#0f0f0f", "#1a1a1a", "#7c3aed"],
  },
  {
    id: "linear",
    name: "Linear",
    description: "Gris froid neutre, indigo sobre, typographie Inter — pro et lisible.",
    swatches: ["#101115", "#181920", "#5e6ad2"],
  },
  {
    id: "raycast",
    name: "Raycast",
    description: "Sombre dramatique, accents corail vifs, plus de glow et d'ombres.",
    swatches: ["#100d16", "#1c1724", "#ff6363"],
  },
  {
    id: "brutalist",
    name: "Brutalist",
    description: "Terminal phosphore vert sur noir absolu, tout en monospace.",
    swatches: ["#000000", "#0a140a", "#00ff41"],
  },
];

const STORAGE_KEY = "camoufox.theme";
const DEFAULT_THEME: ThemeId = "camoufox";

export function getStoredTheme(): ThemeId {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw && THEMES.some((t) => t.id === raw)) return raw as ThemeId;
  } catch {
    /* localStorage may be unavailable in some contexts; fall through. */
  }
  return DEFAULT_THEME;
}

export function applyTheme(id: ThemeId): void {
  document.documentElement.setAttribute("data-theme", id);
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* ignore — preference just won't persist */
  }
}

/* ------------------------------------------------------------------ */
/* Layout (top tabs vs. sidebar)                                       */
/* ------------------------------------------------------------------ */

export type LayoutId = "topbar" | "sidebar";

const LAYOUT_KEY = "camoufox.layout";
const DEFAULT_LAYOUT: LayoutId = "topbar";

export function getStoredLayout(): LayoutId {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (raw === "topbar" || raw === "sidebar") return raw;
  } catch {
    /* ignore */
  }
  return DEFAULT_LAYOUT;
}

export function applyLayout(layout: LayoutId): void {
  document.documentElement.setAttribute("data-layout", layout);
  try {
    localStorage.setItem(LAYOUT_KEY, layout);
  } catch {
    /* ignore */
  }
}
