import { describe, it, expect, vi, beforeEach } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * The UI's reading of the authorization rules has to match the server's.
 *
 * `capabilitiesFromGroups` decides which controls appear. It is not a security
 * boundary -- AppSync and the handlers refuse regardless -- but a wrong answer is
 * still a defect in both directions: too permissive puts back the buttons that only
 * produce errors, too restrictive hides a capability the account has and produces a
 * support question with no message to search for.
 *
 * `portalOutputs` is mocked rather than read. It resolves `amplify_outputs.json`,
 * which `npx ampx sandbox` generates and .gitignore excludes, so a test that depended
 * on its contents would pass locally and fail in CI on a file that is not there.
 */
const SCHEMA = resolve(import.meta.dirname, "../../amplify/data/resource.ts");

/** Loads the hook module with a given set of published outputs. */
async function withOutputs(outputs: {
  enforceRoles: boolean;
  externalAiEnabled: boolean;
  externalShareLinksByRole: Record<string, boolean>;
}) {
  vi.resetModules();
  vi.doMock("../../src/lib/portalOutputs", () => ({
    ...outputs,
    s3ApAlias: "",
    outputsRegion: "",
  }));
  return await import("../../src/hooks/usePortalRole");
}

const ENFORCED = {
  enforceRoles: true,
  externalAiEnabled: false,
  externalShareLinksByRole: {},
};

describe("capabilitiesFromGroups, with the role rules on", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("gives an account in no group nothing but reading", async () => {
    const { capabilitiesFromGroups } = await withOutputs(ENFORCED);
    const caps = capabilitiesFromGroups([]);
    expect(caps.canWrite).toBe(false);
    expect(caps.canAudit).toBe(false);
    expect(caps.hasNoRole).toBe(true);
    expect(caps.roles).toEqual([]);
  });

  it("separates a viewer from an account with no role at all", async () => {
    // The two are both read-only, and the fix differs: one needs a different role,
    // the other needs any role. `hasNoRole` is what picks the wording.
    const { capabilitiesFromGroups } = await withOutputs(ENFORCED);
    const viewer = capabilitiesFromGroups(["viewer"]);
    expect(viewer.canWrite).toBe(false);
    expect(viewer.hasNoRole).toBe(false);
    expect(viewer.roles).toEqual(["viewer"]);
  });

  it("lets a contributor write but not audit", async () => {
    const { capabilitiesFromGroups } = await withOutputs(ENFORCED);
    const caps = capabilitiesFromGroups(["contributor"]);
    expect(caps.canWrite).toBe(true);
    expect(caps.canAudit).toBe(false);
  });

  it("lets an auditor audit but not write", async () => {
    // `auditor` is orthogonal to the read/write ladder, not a rung above `viewer`.
    const { capabilitiesFromGroups } = await withOutputs(ENFORCED);
    const caps = capabilitiesFromGroups(["auditor"]);
    expect(caps.canAudit).toBe(true);
    expect(caps.canWrite).toBe(false);
  });

  it("gives storage-admin both", async () => {
    const { capabilitiesFromGroups } = await withOutputs(ENFORCED);
    const caps = capabilitiesFromGroups(["storage-admin"]);
    expect(caps.canWrite).toBe(true);
    expect(caps.canAudit).toBe(true);
    expect(caps.isAdmin).toBe(true);
  });

  it("takes the most permissive of several roles", async () => {
    const { capabilitiesFromGroups } = await withOutputs(ENFORCED);
    const caps = capabilitiesFromGroups(["viewer", "contributor"]);
    expect(caps.canWrite).toBe(true);
  });

  it("ignores a group that is not a portal role", async () => {
    // Deployments put people in their own groups for path prefixes. One of those must
    // not read as a role, or `team-a` would silently become a write grant.
    const { capabilitiesFromGroups } = await withOutputs(ENFORCED);
    const caps = capabilitiesFromGroups(["team-a"]);
    expect(caps.roles).toEqual([]);
    expect(caps.canWrite).toBe(false);
    expect(caps.hasNoRole).toBe(true);
  });
});

describe("the direct upload path", () => {
  /**
   * `canUploadDirect` answers a different question from `canWrite`, and the difference is
   * the whole reason it exists. The Storage Browser writes to S3 from the browser, so what
   * governs it is the IAM role Cognito selects -- granted per group in `backend.ts` --
   * rather than the AppSync rules. Deriving it from `canWrite` would make the tab appear
   * for accounts that get an S3 AccessDenied and hide it from accounts that do not.
   */
  it("follows the roles backend.ts grants the write to", async () => {
    const { capabilitiesFromGroups } = await withOutputs(ENFORCED);
    expect(capabilitiesFromGroups(["contributor"]).canUploadDirect).toBe(true);
    expect(capabilitiesFromGroups(["storage-admin"]).canUploadDirect).toBe(true);
    expect(capabilitiesFromGroups(["viewer"]).canUploadDirect).toBe(false);
    expect(capabilitiesFromGroups(["auditor"]).canUploadDirect).toBe(false);
    expect(capabilitiesFromGroups([]).canUploadDirect).toBe(false);
  });

  it("stays closed when the role rules are off", async () => {
    // The case that separates it from `canWrite`. With `enforceRoles: false` AppSync lets
    // any signed-in account write, and the IAM grant is unchanged -- so an ungrouped
    // account may write through the API and still cannot upload here.
    const { capabilitiesFromGroups } = await withOutputs({
      ...ENFORCED,
      enforceRoles: false,
    });
    const caps = capabilitiesFromGroups([]);
    expect(caps.canWrite).toBe(true);
    expect(caps.canUploadDirect).toBe(false);
  });
});

describe("capabilitiesFromGroups, with the role rules off", () => {
  it("lets any signed-in account write and audit", async () => {
    // Stated because it is easy to leave in place: while `enforceRoles` is false the
    // schema emits `allow.authenticated()`, so hiding the controls would misdescribe
    // a deployment that does permit them.
    const { capabilitiesFromGroups } = await withOutputs({
      ...ENFORCED,
      enforceRoles: false,
    });
    const caps = capabilitiesFromGroups([]);
    expect(caps.canWrite).toBe(true);
    expect(caps.canAudit).toBe(true);
    // Not "has no role" in the sense the banner means: nothing is being withheld.
    expect(caps.hasNoRole).toBe(false);
  });
});

describe("the external scope", () => {
  it("does not restrict an internal account", async () => {
    const { capabilitiesFromGroups } = await withOutputs(ENFORCED);
    const caps = capabilitiesFromGroups(["contributor", "internal"]);
    expect(caps.isExternal).toBe(false);
    expect(caps.canUseAi).toBe(true);
    expect(caps.canShareLinks).toBe(true);
  });

  it("denies AI and share links by default", async () => {
    const { capabilitiesFromGroups } = await withOutputs(ENFORCED);
    const caps = capabilitiesFromGroups(["contributor", "external"]);
    expect(caps.isExternal).toBe(true);
    expect(caps.canUseAi).toBe(false);
    expect(caps.canShareLinks).toBe(false);
    // Writing is a separate axis: an external contributor exchanging files is the
    // case the external scope exists for.
    expect(caps.canWrite).toBe(true);
  });

  it("allows AI when the deployment opts in", async () => {
    const { capabilitiesFromGroups } = await withOutputs({
      ...ENFORCED,
      externalAiEnabled: true,
    });
    expect(capabilitiesFromGroups(["viewer", "external"]).canUseAi).toBe(true);
  });

  it("allows share links only for the roles named", async () => {
    const { capabilitiesFromGroups } = await withOutputs({
      ...ENFORCED,
      externalShareLinksByRole: { contributor: true, viewer: false },
    });
    expect(capabilitiesFromGroups(["contributor", "external"]).canShareLinks).toBe(true);
    expect(capabilitiesFromGroups(["viewer", "external"]).canShareLinks).toBe(false);
  });

  it("closes the direct upload path whatever the role", async () => {
    // The Upload tab is IAM, not AppSync: `backend.ts` gives the `external` group role no
    // S3 at all, and Cognito selects that role ahead of every other. An external
    // contributor writes through AppSync, where the path prefixes apply, and not here.
    const { capabilitiesFromGroups } = await withOutputs(ENFORCED);
    expect(capabilitiesFromGroups(["contributor", "external"]).canUploadDirect).toBe(false);
    expect(capabilitiesFromGroups(["storage-admin", "external"]).canUploadDirect).toBe(false);
  });

  it("does not let the scope name itself grant share links", async () => {
    // `{"external": true}` is how somebody would naturally write "external users may
    // share", and honouring it would grant every outside caller at once and erase the
    // per-role distinction the setting exists to draw. `share_link_denial_reason` in
    // `shared/portal_external_policy.py` refuses the same way; this is the UI half.
    const { capabilitiesFromGroups } = await withOutputs({
      ...ENFORCED,
      externalShareLinksByRole: { external: true },
    });
    expect(capabilitiesFromGroups(["viewer", "external"]).canShareLinks).toBe(false);
  });
});

describe("the role lists match the schema", () => {
  const schemaRoles = (name: string): string[] => {
    const source = readFileSync(SCHEMA, "utf-8");
    const match = source.match(new RegExp(`const ${name} = \\[([^\\]]*)\\]`));
    expect(match, `${name} not found in data/resource.ts`).toBeTruthy();
    return [...match![1].matchAll(/ROLE_([A-Z_]+)/g)].map((found) => found[1]);
  };

  it("finds both lists", () => {
    // Guards the reader: an empty match would make the comparisons below vacuous.
    expect(schemaRoles("WRITE_ROLES").length).toBe(2);
    expect(schemaRoles("AUDIT_ROLES").length).toBe(2);
  });

  it("writes are the roles the schema names", () => {
    expect(schemaRoles("WRITE_ROLES").sort()).toEqual(["CONTRIBUTOR", "STORAGE_ADMIN"]);
  });

  it("audit is the roles the schema names", () => {
    expect(schemaRoles("AUDIT_ROLES").sort()).toEqual(["AUDITOR", "STORAGE_ADMIN"]);
  });
});
