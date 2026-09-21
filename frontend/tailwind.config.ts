import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#101414",
        panel: "#171d1d",
        line: "#2d3737",
        ink: "#edf4ef",
        muted: "#9aacaa",
        accent: "#45c88a",
        warning: "#f2c14e",
        danger: "#ef7b6f",
      },
    },
  },
  plugins: [],
} satisfies Config;
