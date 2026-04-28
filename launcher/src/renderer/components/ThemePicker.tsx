import { THEMES } from "../themes";
import { useAppStore } from "../store";

/**
 * Visual theme picker. Each tile shows the theme's three signature swatches
 * (bg / surface / accent) and previews a tiny pill+button mock so the user
 * sees the actual color combination before committing. Clicking a tile
 * applies the theme live and persists the choice via the store.
 */
export function ThemePicker() {
  const current = useAppStore((s) => s.theme);
  const setTheme = useAppStore((s) => s.setTheme);

  return (
    <div className="grid grid-cols-2 gap-3">
      {THEMES.map((t) => {
        const active = t.id === current;
        return (
          <button
            type="button"
            key={t.id}
            onClick={() => setTheme(t.id)}
            className={[
              "text-left rounded-lg border p-3 transition-all",
              "hover:scale-[1.01] active:scale-[0.99]",
              active
                ? "border-accent-500 ring-2 ring-accent-500/30 bg-surface-800"
                : "border-surface-700 bg-surface-800/50 hover:border-surface-700/80 hover:bg-surface-800",
            ].join(" ")}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="font-medium text-surface-100 flex items-center gap-2">
                {t.name}
                {active && (
                  <span className="text-[10px] uppercase tracking-wide text-accent-500">
                    actif
                  </span>
                )}
              </div>
              <ThemePreview swatches={t.swatches} />
            </div>
            <p className="text-xs text-surface-100/60 leading-snug">
              {t.description}
            </p>
            <div className="mt-3 flex items-center gap-2">
              <ThemePreviewPill swatches={t.swatches} />
              <ThemePreviewButton swatches={t.swatches} />
            </div>
          </button>
        );
      })}
    </div>
  );
}

/** Three small color circles, one per swatch. */
function ThemePreview({ swatches }: { swatches: [string, string, string] }) {
  return (
    <div className="flex -space-x-1.5">
      {swatches.map((c, i) => (
        <span
          key={i}
          className="w-4 h-4 rounded-full border border-black/40"
          style={{ backgroundColor: c }}
        />
      ))}
    </div>
  );
}

/** A pill rendered with the theme's bg + accent for at-a-glance feedback. */
function ThemePreviewPill({ swatches }: { swatches: [string, string, string] }) {
  const [, surface, accent] = swatches;
  return (
    <span
      className="text-[10px] px-1.5 py-0.5 rounded"
      style={{ backgroundColor: surface, color: accent }}
    >
      label
    </span>
  );
}

/** A tiny button using the theme's accent so the user sees CTA contrast. */
function ThemePreviewButton({ swatches }: { swatches: [string, string, string] }) {
  const [, , accent] = swatches;
  return (
    <span
      className="text-[10px] px-2 py-0.5 rounded text-white"
      style={{ backgroundColor: accent }}
    >
      action
    </span>
  );
}
