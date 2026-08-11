import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  server: {
    /*
     * Hosts the dev server will answer for, beyond localhost.
     *
     * Vite refuses a request whose Host header it does not recognise, which is
     * what stops a malicious page from rebinding DNS to your dev server and
     * reading your source. The consequence is that the procedure documented for
     * checking on a phone -- `cloudflared tunnel --url http://localhost:5173` --
     * could not work: the tunnel forwards its own hostname, and Vite answered
     *
     *     Blocked request. This host ("...trycloudflare.com") is not allowed.
     *
     * A leading dot matches subdomains, so these cover the tunnels the docs
     * mention without opening the server to any hostname at all. `true` would
     * also make the tunnel work, and would give up the protection every time
     * anyone runs the dev server, including when no tunnel is involved.
     *
     * A phone cannot use `http://<LAN-IP>` regardless: sign-in needs
     * `crypto.subtle` and copying a share link needs `navigator.clipboard`,
     * both of which browsers restrict to a secure context. Hence a tunnel, or
     * Amplify Hosting.
     */
    allowedHosts: [".trycloudflare.com", ".ngrok-free.app", ".ngrok.io", ".loca.lt"],
  },
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
