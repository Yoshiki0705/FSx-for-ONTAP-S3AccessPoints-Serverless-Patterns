/**
 * The synth-time checks on the portal's authorization configuration.
 *
 * Every case here deploys without error today and enforces less than it appears to. The
 * point of checking them at synth is that none of them surfaces at runtime: the boundary
 * resolves to "unrestricted", or the grant matches nobody, or the prefix reaches into a
 * sibling directory. A deployment learns nothing until somebody is affected.
 *
 * Run against the real function rather than against the source text, which is why the
 * checks live in their own module. Reading `backend.ts` for the presence of a comparison
 * would confirm the code exists without ever establishing that it fires.
 */
import { describe, it, expect } from "vitest";

import {
  type AuthorizationConfig,
  authorizationConfigProblems,
  validateAuthorizationConfig,
} from "../../amplify/validate-authorization-config";

const ok: AuthorizationConfig = {
  groupApMapping: { "team-a": "team-a-ap-alias" },
  groupPathPrefixes: { "team-a": ["teams/a/", "shared/"] },
  externalDefaults: { shareLinksByRole: { contributor: true, viewer: false } },
  // Named, because this configuration routes a group to its own access point and the
  // Storage Browser's IAM scope has to agree. The wildcard case is asserted below.
  s3ApResourceArns: [
    "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/team-a-ap",
    "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/team-a-ap/object/*",
  ],
};

/** `ok` with one field replaced. */
const withConfig = (overrides: Partial<AuthorizationConfig>): AuthorizationConfig => ({
  ...ok,
  ...overrides,
});

describe("Portal authorization configuration validation", () => {
  it("accepts a configuration that takes effect as written", () => {
    expect(authorizationConfigProblems(ok)).toEqual([]);
    expect(() => validateAuthorizationConfig(ok)).not.toThrow();
  });

  describe("per-group access points against the Storage Browser's IAM scope", () => {
    /**
     * `groupApMapping` gives a group its own access point so its callers run as a different
     * ONTAP identity, and the Lambda handlers apply that routing. The Storage Browser does
     * not go through them -- it calls S3 with the identity pool's credentials -- so on that
     * path the only limit is `s3ApResourceArns`. Naming every access point there cancels the
     * isolation the mapping was written for, and nothing reports it.
     */
    it("rejects a wildcard access point when groups are routed to their own", () => {
      const problems = authorizationConfigProblems(
        withConfig({ s3ApResourceArns: ["arn:aws:s3:*:*:accesspoint/*"] })
      );
      expect(problems).toHaveLength(1);
      expect(problems[0]).toContain("groupApMapping");
      expect(problems[0]).toContain("arn:aws:s3:*:*:accesspoint/*");
      expect(() =>
        validateAuthorizationConfig(
          withConfig({ s3ApResourceArns: ["arn:aws:s3:*:*:accesspoint/*"] })
        )
      ).toThrow();
    });

    it("allows a wildcard when no group is routed", () => {
      // Single-tenant: there is no other access point to reach, so the wildcard takes
      // nothing away. Raising it here would be noise on the default configuration.
      expect(
        authorizationConfigProblems({
          groupApMapping: {},
          externalDefaults: { shareLinksByRole: {} },
          s3ApResourceArns: ["arn:aws:s3:*:*:accesspoint/*"],
        })
      ).toEqual([]);
    });

    it("allows an object-key wildcard on a named access point", () => {
      // Object keys cannot be enumerated in advance, so this wildcard is unavoidable and
      // is not what the check is about. Flagging it would make the check unsatisfiable.
      expect(
        authorizationConfigProblems(
          withConfig({
            s3ApResourceArns: [
              "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/team-a-ap/object/*",
            ],
          })
        )
      ).toEqual([]);
    });

    it("says nothing when the field is absent", () => {
      // A configuration written before this was read still validates.
      const { s3ApResourceArns: _unused, ...withoutArns } = ok;
      expect(authorizationConfigProblems(withoutArns)).toEqual([]);
    });
  });

  it("accepts the shipped defaults", () => {
    // Nothing configured is the compatible state, not a misconfiguration.
    expect(
      authorizationConfigProblems({
        groupApMapping: {},
        externalDefaults: { shareLinksByRole: {} },
      })
    ).toEqual([]);
  });

  it("rejects the scope used as a role key", () => {
    // The reading somebody would naturally write: "external users may share links".
    // It grants nobody, because only roles are consulted.
    const problems = authorizationConfigProblems(
      withConfig({ externalDefaults: { shareLinksByRole: { external: true } } })
    );
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain('"external", which is not a role');
  });

  it("rejects a team group used as a role key", () => {
    const problems = authorizationConfigProblems(
      withConfig({ externalDefaults: { shareLinksByRole: { "team-a": true } } })
    );
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain("not a role");
  });

  it("accepts every declared role as a key", () => {
    expect(
      authorizationConfigProblems(
        withConfig({
          externalDefaults: {
            shareLinksByRole: {
              viewer: false,
              contributor: true,
              "storage-admin": true,
              auditor: false,
            },
          },
        })
      )
    ).toEqual([]);
  });

  it("rejects an access point alias that is blank", () => {
    // Falls back to the deployment default, which is the identity the group was given
    // its own access point to avoid.
    const problems = authorizationConfigProblems(
      withConfig({ groupApMapping: { "team-a": "   " } })
    );
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain("falls back to the default");
  });

  it("rejects a prefix with no trailing separator", () => {
    // "teams/a" also matches "teams/ab/". The boundary is a string comparison.
    const problems = authorizationConfigProblems(
      withConfig({ groupPathPrefixes: { "team-a": ["teams/a"] } })
    );
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain('also matches "teams/ax/"');
  });

  it("rejects a prefix with a leading separator", () => {
    const problems = authorizationConfigProblems(
      withConfig({ groupPathPrefixes: { "team-a": ["/teams/a/"] } })
    );
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain("matches nothing");
  });

  it("rejects an empty prefix list", () => {
    // Reads as "restricted to nothing" and means "unrestricted".
    const problems = authorizationConfigProblems(
      withConfig({ groupPathPrefixes: { "team-a": [] } })
    );
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain("means unrestricted");
  });

  it("reports every problem at once", () => {
    // One per attempted deployment would make fixing three settings take three synths.
    const problems = authorizationConfigProblems({
      groupApMapping: { "team-a": "" },
      groupPathPrefixes: { "team-a": ["teams/a"] },
      externalDefaults: { shareLinksByRole: { external: true } },
    });
    expect(problems).toHaveLength(3);
  });

  it("names the field and the consequence, not only the rule", () => {
    // The reader is an administrator who believed the setting worked. A message that
    // says "invalid" sends them to the schema; this one has to say what is not happening.
    try {
      validateAuthorizationConfig(
        withConfig({ groupPathPrefixes: { "team-a": ["teams/a"] } })
      );
      expect.unreachable("should have thrown");
    } catch (error) {
      const message = (error as Error).message;
      expect(message).toContain('groupPathPrefixes["team-a"]');
      expect(message).toContain("would not take effect");
    }
  });
});
