import { PORTAL_ROLES, PORTAL_SCOPES } from "./portal-groups";

/**
 * The parts of the portal configuration this validation reads.
 *
 * Narrower than `PortalConfig` on purpose, so the checks can be exercised with a few
 * fields instead of a whole deployment's worth of ARNs.
 */
export interface AuthorizationConfig {
  groupApMapping: Record<string, string>;
  groupPathPrefixes?: Record<string, string[]>;
  externalDefaults: {
    shareLinksByRole: Record<string, boolean>;
  };
  /**
   * The IAM resource scope of the Storage Browser's direct path to S3.
   *
   * Optional so a test can leave it out, and so a configuration written before this was
   * read still validates.
   */
  s3ApResourceArns?: string[];
}

/**
 * Whether an ARN names any access point rather than one.
 *
 * True when the access-point name itself is a wildcard, as in
 * `arn:aws:s3:*:*:accesspoint/*` and the object-level ARN beneath it.
 *
 * False when the access point is named and only the object key is wildcarded. Object keys
 * cannot be enumerated in advance, so that wildcard is unavoidable and is not what this
 * asks about.
 */
function grantsAnyAccessPoint(arn: string): boolean {
  const marker = ":accesspoint/";
  const at = arn.indexOf(marker);
  if (at === -1) return false;
  const name = arn.slice(at + marker.length).split("/")[0];
  return name.includes("*");
}

/**
 * Configuration that is set and inert.
 *
 * Every case below deploys successfully, answers requests, and enforces less than the
 * person who wrote it believes. None of them produces an error at runtime: the boundary
 * resolves to "unrestricted", or the grant matches nobody, or the prefix also matches a
 * sibling directory. Silence in that direction is why they are collected here and
 * raised at synth.
 *
 * Kept in its own module, taking the configuration as an argument, so the checks can be
 * run against a crafted configuration in a test. Inside `backend.ts` they could only be
 * asserted by reading the source, which would confirm the code is present without ever
 * establishing that it fires.
 *
 * @param config - The configuration to check.
 * @returns One message per problem found, in the order the fields were read. Empty when
 *   the configuration takes effect as written.
 */
export function authorizationConfigProblems(config: AuthorizationConfig): string[] {
  const problems: string[] = [];

  // A role-keyed setting matched against something that is not a role. The Python side
  // consults only roles, so a scope or a team name here grants nothing -- and
  // `{"external": true}` is exactly how somebody would write "external users may share
  // links", which makes the silence expensive.
  for (const role of Object.keys(config.externalDefaults.shareLinksByRole)) {
    if (!(PORTAL_ROLES as readonly string[]).includes(role)) {
      problems.push(
        `externalDefaults.shareLinksByRole has the key "${role}", which is not a role. ` +
          `Roles are ${PORTAL_ROLES.join(", ")}. Scopes (${PORTAL_SCOPES.join(", ")}) and ` +
          "team groups are not roles, and a non-role key grants nothing."
      );
    }
  }

  // Per-group access points, and an IAM scope that reaches all of them.
  //
  // `groupApMapping` gives a group its own access point so its callers run as a different
  // ONTAP identity. That routing is applied by the Lambda handlers. The Storage Browser
  // does not go through them -- it calls S3 with the identity pool's credentials -- so on
  // that path the only limit is `s3ApResourceArns`. Left naming every access point, a
  // `contributor` in one group reaches another group's access point directly, and the
  // isolation the mapping was written for is absent exactly where nothing reports it.
  //
  // Raised only when both are present. The wildcard alone is the single-tenant case, where
  // there is no other access point to reach.
  const wildcardArns = (config.s3ApResourceArns ?? []).filter(grantsAnyAccessPoint);
  if (Object.keys(config.groupApMapping).length > 0 && wildcardArns.length > 0) {
    problems.push(
      `groupApMapping routes ${Object.keys(config.groupApMapping).length} group(s) to their ` +
        `own access points, but s3ApResourceArns grants every access point ` +
        `(${wildcardArns.join(", ")}). The Storage Browser reaches S3 directly, so on that ` +
        "path the mapping does not apply. Name the access points this deployment uses."
    );
  }

  // An access point mapping to an empty alias falls back to the deployment default,
  // which is the identity the group was given its own access point in order to avoid.
  for (const [group, alias] of Object.entries(config.groupApMapping)) {
    if (!alias.trim()) {
      problems.push(
        `groupApMapping["${group}"] is empty, so this group falls back to the default ` +
          "access point and acts as the default ONTAP identity."
      );
    }
  }

  for (const [group, prefixes] of Object.entries(config.groupPathPrefixes ?? {})) {
    // An empty list reads as "restricted to nothing" and means "unrestricted".
    if (prefixes.length === 0) {
      problems.push(
        `groupPathPrefixes["${group}"] is an empty list, which means unrestricted rather ` +
          "than restricted to nothing. Remove the entry if that is intended."
      );
    }
    for (const prefix of prefixes) {
      // "teams/a" also matches "teams/ab/". The boundary is a string comparison, so a
      // missing separator quietly widens it to a sibling directory.
      if (!prefix.endsWith("/")) {
        problems.push(
          `groupPathPrefixes["${group}"] contains "${prefix}", which does not end in "/". ` +
            `The boundary compares strings, so this also matches "${prefix}x/".`
        );
      }
      if (prefix.startsWith("/")) {
        problems.push(
          `groupPathPrefixes["${group}"] contains "${prefix}", which starts with "/". ` +
            "Object keys have no leading slash, so this matches nothing."
        );
      }
    }
  }

  return problems;
}

/**
 * Raise if any part of the authorization configuration would not take effect.
 *
 * @param config - The configuration to check.
 * @throws When at least one setting is inert.
 */
export function validateAuthorizationConfig(config: AuthorizationConfig): void {
  const problems = authorizationConfigProblems(config);
  if (problems.length === 0) return;
  throw new Error(
    "Portal authorization configuration is set but would not take effect:\n\n" +
      problems.map((problem) => `  - ${problem}`).join("\n") +
      "\n\nEach of these deploys without error and enforces less than it appears to."
  );
}
