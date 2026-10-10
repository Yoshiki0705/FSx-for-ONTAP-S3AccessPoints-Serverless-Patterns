// @vitest-environment node
//
// The AppSync resolver for the recovery-points query forwards every parameter to the
// handler. This pins that for the two keys #461 relies on, `backupVaultAccountId` and
// `backupVaultRegion`, so a later "tidy-up" into an allow-list of keys cannot silently
// drop them while the panel keeps rendering.
//
// The resolver runs in the AppSync JavaScript runtime, which this repository has no
// harness for, and `@aws-appsync/utils` is not a dependency of this package. The
// resolver's own `request` function is therefore run here against a stand-in `util`,
// not re-implemented: the source is read from the file and evaluated.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const RESOLVER = resolve(import.meta.dirname, "../../amplify/data/resolvers/recovery-points-dispatch.js");

type Request = (ctx: {
  arguments: { action: string; params?: unknown };
  identity: { username: string };
}) => { operation: string; payload: Record<string, unknown> };

/** The resolver's `request`, with its one import replaced by a stand-in. */
function loadRequest(): Request {
  const source = readFileSync(RESOLVER, "utf-8")
    .replace(/^import .*$/m, "")
    .replace(/^export function /gm, "function ");
  // The resolver is repository source read from a fixed path above, not input.
  const build = new Function("util", `${source}\nreturn request;`) as (util: unknown) => Request;
  return build({ error: () => undefined });
}

const request = loadRequest();

const ctx = (params: unknown, action = "listRecoveryPoints") => ({
  arguments: { action, params },
  identity: { username: "portal-user" },
});

describe("recovery-points resolver", () => {
  it("forwards the shared-vault and Region keys to the handler", () => {
    const { payload } = request(
      ctx({
        backupVaultName: "shared-vault",
        backupVaultAccountId: "111122223333",
        backupVaultRegion: "us-east-1",
        maxResults: 100,
      }),
    );

    expect(payload.backupVaultName).toBe("shared-vault");
    expect(payload.backupVaultAccountId).toBe("111122223333");
    expect(payload.backupVaultRegion).toBe("us-east-1");
    expect(payload.maxResults).toBe(100);
  });

  it("accepts params as the JSON string the client sends", () => {
    const { payload } = request(ctx(JSON.stringify({ backupVaultRegion: "us-east-1" }), "listSharedBackupVaults"));

    expect(payload.backupVaultRegion).toBe("us-east-1");
    expect(payload.action).toBe("listSharedBackupVaults");
  });

  it("does not let a caller override the action or the identity", () => {
    const { payload } = request(ctx({ action: "somethingElse", userId: "someone-else" }));

    expect(payload.action).toBe("listRecoveryPoints");
    expect(payload.userId).toBe("portal-user");
  });
});
