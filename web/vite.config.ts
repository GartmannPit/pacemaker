import { defineConfig } from "vite";

// CSP ohne Inline-Anteile (Plan §3.2): keine eingebetteten Assets, kein Preload-Polyfill.
// Entwicklung bevorzugt per `pnpm build:watch` gegen den Hybrid-Server (gleiche CSP).
export default defineConfig({
  build: {
    assetsInlineLimit: 0,
    modulePreload: { polyfill: false },
    sourcemap: false,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8080",
      "/healthz": "http://127.0.0.1:8080",
    },
  },
});
