/** @type {import('tailwindcss').Config} */
// Colors are wired through CSS custom properties so we can swap themes at
// runtime without rebuilding. Each theme is defined in `themes.css` and
// activated via `data-theme="..."` on the <html> element.
const cssVar = (name) => `rgb(var(${name}) / <alpha-value>)`;

module.exports = {
  content: [
    "./index.html",
    "./src/renderer/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          50:  cssVar("--color-surface-50"),
          100: cssVar("--color-surface-100"),
          200: cssVar("--color-surface-200"),
          700: cssVar("--color-surface-700"),
          800: cssVar("--color-surface-800"),
          900: cssVar("--color-surface-900"),
        },
        accent: {
          500: cssVar("--color-accent-500"),
          600: cssVar("--color-accent-600"),
        },
        // Semantic tokens — used by new components in addition to the legacy
        // surface/accent palette (which all existing classes still consume).
        bg:        cssVar("--color-bg"),
        elevated:  cssVar("--color-elevated"),
        border:    cssVar("--color-border"),
        muted:     cssVar("--color-muted"),
        fg:        cssVar("--color-fg"),
        "fg-muted": cssVar("--color-fg-muted"),
        success:   cssVar("--color-success"),
        warning:   cssVar("--color-warning"),
        danger:    cssVar("--color-danger"),
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
        display: ["var(--font-display)"],
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius)",
        lg: "var(--radius-lg)",
      },
      boxShadow: {
        soft: "var(--shadow-soft)",
        glow: "var(--shadow-glow)",
      },
    },
  },
  plugins: [],
};
