// @vitest-environment node
//
// The portal's defaults, asserted by loading the configuration rather than by reading it.
//
// Source-text assertions elsewhere pin the expressions; this pins the answer. The two are
// not the same check: a source assertion confirms that `!== "false"` is written down, and
// this confirms what an unset environment actually resolves to.
//
// Node environment, not jsdom: `portal-config` is reached from `backend.ts`, and
// `@aws-amplify/backend` refuses to load in a browser environment.
//
// What is deliberately not asserted here: that setting the environment variables opts out.
// `amplify/portal-config.ts` is gitignored and CI copies `portal-config.example.ts` over
// it, and the example holds literals rather than environment lookups -- so an opt-out
// assertion would pass locally and fail in CI. Every case below holds in both shapes,
// which is what makes it safe to assert: the example's literals are the restrictive values,
// and the real file's expressions resolve to them.
//
// The consequence is that the misspelling case below is a real test of the polarity only
// where the real configuration exists, and a trivially passing one in CI, where the example
// ignores the environment. Stated rather than left to be discovered: the alternative was an
// assertion on the real file's source, which fails in CI outright.
import { describe, it, expect, vi, beforeEach } from "vitest";

beforeEach(() => {
  vi.resetModules();
  vi.unstubAllEnvs();
});

/** Load the configuration under a given environment. */
async function loadConfig(env: Record<string, string> = {}) {
  for (const [name, value] of Object.entries(env)) vi.stubEnv(name, value);
  const module = await import("../../amplify/portal-config");
  return module.config;
}

describe("Portal configuration defaults", () => {
  it("closes registration and enforces roles when nothing is set", async () => {
    // Both were the other way round, on a compatibility argument. Nothing downstream
    // depends on this repository, so the default is the safe one.
    const config = await loadConfig();
    expect(config.signIn.selfSignUpEnabled).toBe(false);
    expect(config.enforceRoles).toBe(true);
  });

  it("withholds the AI endpoints and share links from outside members", async () => {
    const config = await loadConfig();
    expect(config.externalDefaults.aiEnabled).toBe(false);
    // Empty denies every role, since a role absent from the map is denied.
    expect(config.externalDefaults.shareLinksByRole).toEqual({});
  });

  it("stays restrictive when the variable is misspelled", async () => {
    // The reason the polarity was chosen. `AMPLIFY_PORTAL_ENFORCE_ROLES=treu` used to
    // read as "not true" and silently removed the authorization rules; now the word that
    // has to be spelled correctly is the one that removes them.
    const config = await loadConfig({
      AMPLIFY_PORTAL_SELF_SIGN_UP: "ture",
      AMPLIFY_PORTAL_ENFORCE_ROLES: "flase",
      AMPLIFY_PORTAL_EXTERNAL_AI_ENABLED: "yes",
    });
    expect(config.signIn.selfSignUpEnabled).toBe(false);
    expect(config.enforceRoles).toBe(true);
    expect(config.externalDefaults.aiEnabled).toBe(false);
  });
});
