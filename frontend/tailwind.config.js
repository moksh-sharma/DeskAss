/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: "#1e293b",
          soft: "#334155",
          muted: "#64748b",
          faint: "#94a3b8",
        },
        frost: {
          50: "rgba(255, 255, 255, 0.92)",
          100: "rgba(255, 255, 255, 0.75)",
          200: "rgba(255, 255, 255, 0.55)",
          300: "rgba(255, 255, 255, 0.38)",
        },
        accent: {
          DEFAULT: "#6366f1",
          hover: "#4f46e5",
          light: "#818cf8",
          soft: "#a5b4fc",
          glow: "rgba(99, 102, 241, 0.22)",
        },
        aurora: {
          sky: "#bae6fd",
          lavender: "#ddd6fe",
          peach: "#fed7aa",
          rose: "#fecdd3",
          mint: "#a7f3d0",
        },
        severity: {
          healthy: "#059669",
          info: "#0284c7",
          warning: "#d97706",
          critical: "#dc2626",
        },
        /* Legacy aliases - mapped to light theme in components */
        base: {
          900: "rgba(255, 255, 255, 0.25)",
          850: "rgba(255, 255, 255, 0.45)",
          800: "rgba(255, 255, 255, 0.55)",
          750: "rgba(255, 255, 255, 0.40)",
          700: "rgba(255, 255, 255, 0.65)",
          600: "rgba(148, 163, 184, 0.35)",
        },
        "content-primary": "#0f172a",
        "content-secondary": "#334155",
        "content-body": "#475569",
        "content-muted": "#64748b",
        "content-faint": "#94a3b8",
      },
      fontFamily: {
        sans: [
          "Segoe UI Variable",
          "Segoe UI",
          "system-ui",
          "-apple-system",
          "sans-serif",
        ],
        mono: ["Cascadia Code", "JetBrains Mono", "Consolas", "monospace"],
      },
      boxShadow: {
        glass: "0 8px 32px rgba(99, 102, 241, 0.08), 0 2px 8px rgba(15, 23, 42, 0.04), inset 0 1px 0 rgba(255, 255, 255, 0.85)",
        "glass-sm": "0 4px 16px rgba(99, 102, 241, 0.06), 0 1px 4px rgba(15, 23, 42, 0.03), inset 0 1px 0 rgba(255, 255, 255, 0.8)",
        "glass-lg": "0 16px 48px rgba(99, 102, 241, 0.12), 0 4px 16px rgba(15, 23, 42, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.9)",
        glow: "0 0 40px rgba(99, 102, 241, 0.18)",
        "glow-sm": "0 0 20px rgba(99, 102, 241, 0.12)",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "accent-shine": "linear-gradient(135deg, #6366f1 0%, #818cf8 50%, #a78bfa 100%)",
        "user-bubble": "linear-gradient(135deg, #6366f1 0%, #7c3aed 100%)",
      },
      animation: {
        "float-slow": "float 8s ease-in-out infinite",
        "float-slower": "float 12s ease-in-out infinite reverse",
        shimmer: "shimmer 3s ease-in-out infinite",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translate(0, 0) scale(1)" },
          "50%": { transform: "translate(12px, -18px) scale(1.04)" },
        },
        shimmer: {
          "0%, 100%": { opacity: "0.5" },
          "50%": { opacity: "0.85" },
        },
      },
    },
  },
  plugins: [],
};
