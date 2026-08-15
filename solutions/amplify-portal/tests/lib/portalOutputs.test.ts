/**
 * Guards the wiring between the generated outputs and the Upload tab.
 *
 * `src/lib/portalOutputs.ts` reads `amplify_outputs.json` through
 * `import.meta.glob`, which returns an empty record for a path that matches
 * nothing. A typo in that path therefore fails the same way a missing deployment
 * does: `s3ApAlias` is "", the Upload tab reports "not configured", and no error
 * appears anywhere. This compares the module's value against the file itself, so
 * the glob has to be resolving.
 *
 * Skipped when `amplify_outputs.json` is absent -- a fresh clone and CI have no
 * sandbox, and the empty fallback is the correct answer there.
 */
import { describe, it, expect } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const OUTPUTS_PATH = resolve(import.meta.dirname, "../../amplify_outputs.json");
const deployed = existsSync(OUTPUTS_PATH);

describe("portalOutputs", () => {
  it.runIf(deployed)("reads the values the backend published", async () => {
    const onDisk = JSON.parse(readFileSync(OUTPUTS_PATH, "utf-8")) as {
      custom?: { s3ApAlias?: string; region?: string };
    };
    const { s3ApAlias, outputsRegion } = await import("../../src/lib/portalOutputs");

    expect(s3ApAlias).toBe(onDisk.custom?.s3ApAlias ?? "");
    expect(outputsRegion).toBe(onDisk.custom?.region ?? "");
    // The deployed sandbox is expected to carry both; an empty alias here means
    // `s3ApAlias` is unset in amplify/portal-config.ts.
    expect(s3ApAlias).not.toBe("");
    expect(outputsRegion).not.toBe("");
  });

  it.skipIf(deployed)("falls back to empty without a deployment", async () => {
    const { s3ApAlias } = await import("../../src/lib/portalOutputs");
    expect(s3ApAlias).toBe("");
  });
});
