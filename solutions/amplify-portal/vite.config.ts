import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // import.meta.dirname, not __dirname: Vite 8 warns that __dirname is
      // unsupported by `configLoader: 'native'`, which becomes the default in a
      // future major.
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    // tests/e2e holds Playwright specs, which import @playwright/test. That is
    // intentionally not a package.json dependency (the e2e workflow provisions
    // it via npx), so Vitest must not try to collect those files.
    exclude: ["node_modules/**", "dist/**", "tests/e2e/**"],
  },
});
