import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "rgb(var(--color-canvas) / <alpha-value>)",
        surface: "rgb(var(--color-surface) / <alpha-value>)",
        "surface-raised": "rgb(var(--color-surface-raised) / <alpha-value>)",
        panel: "rgb(var(--color-surface) / <alpha-value>)",
        "panel-raised": "rgb(var(--color-surface-raised) / <alpha-value>)",
        line: "rgb(var(--color-line) / <alpha-value>)",
        ink: "rgb(var(--color-ink) / <alpha-value>)",
        muted: "rgb(var(--color-muted) / <alpha-value>)",
        positive: "rgb(var(--color-positive) / <alpha-value>)",
        accent: "rgb(var(--color-positive) / <alpha-value>)",
        caution: "rgb(var(--color-caution) / <alpha-value>)",
        warning: "rgb(var(--color-caution) / <alpha-value>)",
        failure: "rgb(var(--color-failure) / <alpha-value>)",
        danger: "rgb(var(--color-failure) / <alpha-value>)",
        selection: "rgb(var(--color-selection) / <alpha-value>)",
        "control-outline": "rgb(var(--color-control-outline) / <alpha-value>)",
        "chart-1": "rgb(var(--color-chart-1) / <alpha-value>)",
        "chart-2": "rgb(var(--color-chart-2) / <alpha-value>)",
        "chart-3": "rgb(var(--color-chart-3) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "SFMono-Regular", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
