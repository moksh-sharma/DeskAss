import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import electron from "vite-plugin-electron";
import renderer from "vite-plugin-electron-renderer";
import { resolve } from "node:path";

export default defineConfig({
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  plugins: [
    react(),
    electron([
      {
        // Main process.
        entry: "electron/main.ts",
        vite: {
          build: {
            outDir: "dist-electron",
          },
        },
      },
      {
        // Preload script.
        entry: "electron/preload.ts",
        onstart(args) {
          args.reload();
        },
        vite: {
          build: {
            outDir: "dist-electron",
          },
        },
      },
    ]),
    renderer(),
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8003",
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
