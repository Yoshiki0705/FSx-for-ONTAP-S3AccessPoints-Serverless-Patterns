/**
 * Who the Storage Browser's direct path to S3 lets in.
 *
 * This is the one authorization decision in the portal that AppSync does not make. The
 * Upload tab calls S3 from the browser with identity pool credentials, so `enforceRoles`
 * and the path prefixes -- both enforced in the Lambda handlers -- do not apply, and the
 * selected IAM role is the whole of the control.
 *
 * Asserted against the exported mapping rather than against `backend.ts` source text.
 * Grepping for `"s3:PutObject"` would confirm a write grant exists somewhere and say
 * nothing about which group receives it, which is the only question that matters here.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  DIRECT_S3_BY_GROUP,
  S3_READ_ACTIONS,
  S3_WRITE_ACTIONS,
  directS3Problems,
  nagAcknowledgeableWildcards,
} from "../../amplify/direct-s3-access";
import { ALL_PORTAL_GROUPS } from "../../amplify/portal-groups";

const actionsFor = (group: string): string[] =>
  DIRECT_S3_BY_GROUP.find((entry) => entry.group === group)?.actions ?? [];
const precedenceOf = (group: string): number => {
  const entry = DIRECT_S3_BY_GROUP.find((found) => found.group === group);
  expect(entry, `${group} has no entry`).toBeTruthy();
  return entry!.precedence;
};

describe("what each group may do on the direct path", () => {
  it("lets contributor and storage-admin write", () => {
    for (const group of ["contributor", "storage-admin"]) {
      expect(actionsFor(group), group).toEqual(
        expect.arrayContaining([...S3_READ_ACTIONS, ...S3_WRITE_ACTIONS])
      );
    }
  });

  it("gives viewer, auditor and internal reads and no writes", () => {
    for (const group of ["viewer", "auditor", "internal"]) {
      expect(actionsFor(group), group).toEqual(S3_READ_ACTIONS);
      for (const write of S3_WRITE_ACTIONS) {
        expect(actionsFor(group), group).not.toContain(write);
      }
    }
  });

  it("gives the external scope nothing at all", () => {
    // Not read-only: read-only would still be unconfined. The prefixes that define an
    // external member's reach cannot be expressed on a role every external member
    // shares, so the direct path is closed and the AppSync path is the only way in.
    expect(actionsFor("external")).toEqual([]);
  });

  it("does not grant a bucket-wide delete to anybody who cannot write", () => {
    for (const { group, actions } of DIRECT_S3_BY_GROUP) {
      if (!actions.includes("s3:PutObject")) {
        expect(actions, group).not.toContain("s3:DeleteObject");
      }
    }
  });
});

describe("which group Cognito selects", () => {
  /**
   * Precedence is the mechanism, so these assert the orderings the design depends on
   * rather than the numbers themselves. Zero is the highest priority, and the role of
   * the lowest-numbered group a user belongs to becomes `cognito:preferred_role`.
   */
  it("puts the external scope ahead of every role", () => {
    // Otherwise an external contributor would be selected onto the contributor role and
    // write anywhere in the access point, which is the bypass this exists to close.
    for (const role of ["storage-admin", "contributor", "viewer", "auditor"]) {
      expect(precedenceOf("external")).toBeLessThan(precedenceOf(role));
    }
  });

  it("puts the internal scope behind every role", () => {
    // Otherwise every internal member would be selected onto one shared role and the
    // role axis would stop deciding anything.
    for (const role of ["storage-admin", "contributor", "viewer", "auditor"]) {
      expect(precedenceOf("internal")).toBeGreaterThan(precedenceOf(role));
    }
  });

  it("prefers the more permissive of two roles", () => {
    // Matches how AppSync combines roles: holding several grants the most permissive.
    // Amplify's default -- the index in ALL_PORTAL_GROUPS -- gets this backwards, which
    // is why precedence is set explicitly.
    expect(precedenceOf("storage-admin")).toBeLessThan(precedenceOf("contributor"));
    expect(precedenceOf("contributor")).toBeLessThan(precedenceOf("viewer"));
  });
});

describe("directS3Problems", () => {
  it("passes on the groups the portal actually declares", () => {
    expect(directS3Problems([...ALL_PORTAL_GROUPS])).toEqual([]);
  });

  it("reports a declared group with no entry", () => {
    // The dangerous direction: the group keeps an empty role, and because Cognito selects
    // it for its members, adding the group to widen access narrows it instead.
    const problems = directS3Problems([...ALL_PORTAL_GROUPS, "reviewer"]);
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain("reviewer");
    expect(problems[0]).toContain("empty role");
  });

  it("reports an entry naming a group nobody declares", () => {
    const problems = directS3Problems(
      [...ALL_PORTAL_GROUPS].filter((group) => group !== "auditor")
    );
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain("auditor");
    expect(problems[0]).toContain("matches nobody");
  });

  it("reports two groups sharing a precedence", () => {
    // Documented Cognito behaviour: with two groups at the same precedence and different
    // role ARNs, `cognito:preferred_role` is not set at all, so the identity pool falls
    // back to the default authenticated role. Both groups' members would quietly get the
    // read-only fallback instead of their own grant.
    const original = DIRECT_S3_BY_GROUP[1].precedence;
    DIRECT_S3_BY_GROUP[1].precedence = DIRECT_S3_BY_GROUP[2].precedence;
    try {
      const problems = directS3Problems([...ALL_PORTAL_GROUPS]);
      expect(problems.some((problem) => problem.includes("share precedence"))).toBe(true);
    } finally {
      DIRECT_S3_BY_GROUP[1].precedence = original;
    }
  });
});

describe("nagAcknowledgeableWildcards", () => {
  it("keeps an access-point wildcard", () => {
    expect(
      nagAcknowledgeableWildcards([
        "arn:aws:s3:*:*:accesspoint/*",
        "arn:aws:s3:*:*:accesspoint/*/object/*",
      ])
    ).toHaveLength(2);
  });

  it("drops an ARN with no wildcard", () => {
    // No wildcard means no IAM5 finding, so acknowledging it would suppress something that
    // was never raised.
    expect(nagAcknowledgeableWildcards(["arn:aws:s3:::plain-bucket"])).toEqual([]);
  });

  it("drops an ARN whose own form carries a second `::`", () => {
    // `Validations.acknowledge` splits the id on `::` to separate an optional prefix, and
    // throws on more than one. The granular id already contains one inside `[Resource::…]`,
    // so `arn:aws:s3:::bucket/*` makes it unacceptable and the finding stays reported.
    // Passing it through would break synth rather than suppress anything.
    expect(nagAcknowledgeableWildcards(["arn:aws:s3:::demo-bucket/*"])).toEqual([]);
  });

  it("produces ids with exactly one `::` when the prefix is added", () => {
    // The property the filter exists to guarantee, checked the way the API checks it.
    for (const arn of nagAcknowledgeableWildcards([
      "arn:aws:s3:*:*:accesspoint/*",
      "arn:aws:s3:*:*:accesspoint/*/object/*",
      "arn:aws:s3:::demo-bucket/*",
    ])) {
      expect(`AwsSolutions-IAM5[Resource::${arn}]`.split("::")).toHaveLength(2);
    }
  });
});

describe("backend.ts applies the mapping", () => {
  const backendSource = readFileSync(
    resolve(import.meta.dirname, "../../amplify/backend.ts"),
    "utf-8"
  );

  it("stops the deployment when the mapping and the groups disagree", () => {
    // The validator returning a list is worth nothing if nobody throws on it.
    expect(backendSource).toContain("directS3Problems(Object.keys(authResources.groups))");
    expect(backendSource).toMatch(/directS3Issues\.length > 0[\s\S]{0,120}throw new Error/);
  });

  it("grants the default authenticated role reads only", () => {
    // This is the role an ungrouped account assumes, and the fallback for an ambiguous
    // one. It carried PutObject and DeleteObject, and an ungrouped account was measured
    // writing to a prefix no group is granted.
    expect(backendSource).toContain(
      'grantS3(authenticatedRole, "StorageBrowserS3APAccess", S3_READ_ACTIONS)'
    );
    expect(backendSource).not.toMatch(/grantS3\(\s*authenticatedRole[^)]*S3_WRITE_ACTIONS/);
  });

  it("sets the precedence rather than leaving Amplify's index", () => {
    expect(backendSource).toContain("cfnUserGroup.precedence = precedence");
  });
});
