/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        base: {
          900: "#0b0f17",
          800: "#111827",
          750: "#161e2e",
          700: "#1f2937",
          600: "#374151",
        },
        accent: {
          DEFAULT: "#3b82f6",
          hover: "#2563eb",
        },
        severity: {
          healthy: "#22c55e",
          info: "#38bdf8",
          warning: "#f59e0b",
          critical: "#ef4444",
        },
        /* Flat names so @apply text-content-* works in CSS */
        "content-primary": "#f3f4f6",
        "content-secondary": "#e5e7eb",
        "content-body": "#d1d5db",
        "content-muted": "#9ca3af",
        "content-faint": "#6b7280",
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
