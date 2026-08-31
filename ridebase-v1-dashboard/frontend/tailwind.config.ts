import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#08090b",
          900: "#0c0e12",
          850: "#111318",
          800: "#15181e",
          700: "#1b1f27",
          border: "#242933",
        },
        rb: {
          orange: "#ff6a1a",
          "orange-soft": "rgba(255,106,26,0.14)",
          cyan: "#22d3ee",
          "cyan-soft": "rgba(34,211,238,0.12)",
        },
        fg: {
          DEFAULT: "#f3f4f6",
          muted: "#98a2b3",
          faint: "#5b6472",
        },
        ok: "#34d399",
        warn: "#fbbf24",
        bad: "#f87171",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: {
        xl: "12px",
        "2xl": "16px",
      },
      maxWidth: { screen: "1440px" },
    },
  },
  plugins: [],
};
export default config;
