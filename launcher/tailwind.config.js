/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/renderer/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          50: "#fafafa",
          100: "#f3f3f3",
          200: "#e5e5e5",
          700: "#262626",
          800: "#1a1a1a",
          900: "#0f0f0f",
        },
        accent: {
          500: "#7c3aed",
          600: "#6d28d9",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
