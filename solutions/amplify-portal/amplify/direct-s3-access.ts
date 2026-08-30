/**
 * Who may reach S3 directly from the browser, and in what order Cognito decides.
 *
 * The Upload tab (`@aws-amplify/ui-react-storage`) does not call AppSync. It calls S3
 * with the identity pool's credentials, so `enforceRoles` and the path prefixes -- both
 * enforced in the Lambda handlers -- have no bearing on it. Whatever the selected IAM
 * role grants is what that tab can do.
 *
 * Its own module, and expressed as data, for the reason `validate-authorization-config.ts`
 * gives: reading `backend.ts` for the presence of a policy statement would confirm the
 * code exists without establishing what it grants to whom. Here the mapping is the thing
 * under test.
 *
 * Measured behaviour this encodes (deployed pool, 2026-08-27)
 * ----------------------------------------------------------
 * Amplify gives every group declared in `defineAuth` its own IAM role, sets it as the
 * group's `RoleArn`, and attaches the identity pool with `Type: Token`. Cognito then
 * hands out `cognito:preferred_role`: the role of the member group with the **lowest**
 * precedence value. Confirmed on a user in `contributor` + `external`, whose credentials
 * came back as the contributor group role.
 *
 * Two consequences followed, and both were wrong before this existed:
 *
 *   Those group roles are created empty. A user in any group therefore had no S3 access
 *   at all -- `AccessDenied` on ListBucket -- so the Upload tab was already broken for
 *   everybody who had been given a role.
 *
 *   A user in no group fell back to the default authenticated role, which carried
 *   PutObject and DeleteObject. Measured: an ungrouped account wrote successfully to a
 *   prefix that no `groupPathPrefixes` entry grants.
 */

import {
  ROLE_AUDITOR,
  ROLE_CONTRIBUTOR,
  ROLE_STORAGE_ADMIN,
  ROLE_VIEWER,
  SCOPE_EXTERNAL,
  SCOPE_INTERNAL,
} from "./portal-groups";

/** Browsing and downloading. What every group that reaches S3 at all receives. */
export const S3_READ_ACTIONS = ["s3:GetObject", "s3:ListBucket", "s3:GetBucketLocation"];

/**
 * Uploading and deleting.
 *
 * The same two roles `WRITE_ROLES` names in `data/resource.ts`, so the direct path and
 * the AppSync path agree on who may write. They are enforced by different mechanisms and
 * would not otherwise be kept in step.
 */
export const S3_WRITE_ACTIONS = ["s3:PutObject", "s3:DeleteObject"];

/**
 * The configured ARNs with a wildcard account or region replaced by this deployment's.
 *
 * `s3ApResourceArns` ships as `arn:aws:s3:*:*:accesspoint/*`, and the two `*` in the region
 * and account positions grant every access point in every account this principal could
 * reach. Nothing needs that: an access point is addressed by an alias that resolves within
 * one account, so a deployment reaching another account's access point could not work
 * anyway -- that access point's own policy would have to name this principal.
 *
 * So the account and region are filled in from the deployment. This is a narrowing of what
 * the configuration asked for, which is why it is a named function with tests rather than
 * an inline edit: the resulting policy is what the operator can read in the template, and
 * `portal-config.example.ts` says it happens.
 *
 * What it does *not* do is narrow the access point name. That is the wildcard that matters
 * for tenant isolation, and only the operator knows which access points exist;
 * `authorizationConfigProblems` refuses it at synth once `groupApMapping` is in use.
 *
 * Fields other than a bare `*` are left alone, and so is anything that is not a six-field
 * S3 ARN. A plain bucket ARN carries empty region and account fields by design
 * (`arn:aws:s3:::bucket`), and filling those would break it.
 *
 * @param arns The configured resource ARNs.
 * @param scope The deployment's account and region. CDK pseudo-parameters are expected, so
 *   the value resolves per stack at deploy time.
 */
export function scopeS3ApArns(
  arns: readonly string[],
  scope: { account: string; region: string }
): string[] {
  return arns.map((arn) => {
    const parts = arn.split(":");
    // arn : partition : service : region : account : resource — and the resource may
    // itself contain colons, so anything shorter is not an ARN this should touch.
    if (parts.length < 6 || parts[0] !== "arn" || parts[2] !== "s3") return arn;
    const [prefix, partition, service, region, account, ...resource] = parts;
    return [
      prefix,
      partition,
      service,
      region === "*" ? scope.region : region,
      account === "*" ? scope.account : account,
      ...resource,
    ].join(":");
  });
}

export type DirectS3Grant = {
  group: string;
  /** Cognito precedence. Lower wins; 0 is the highest priority. */
  precedence: number;
  actions: string[];
};

/**
 * The grant per group, and the precedence that decides which one applies.
 *
 * Precedence has to be stated rather than left to Amplify, which assigns each group the
 * index it occupies in `ALL_PORTAL_GROUPS`. That order puts `viewer` ahead of
 * `contributor`, so an account holding both would be selected down to read-only -- the
 * opposite of how the AppSync rules combine roles, where holding several grants the most
 * permissive.
 *
 * `external` is first, and that is the load-bearing choice. Exactly one role is selected,
 * so a single ordering can honour only one of the two axes, and for an external member the
 * scope has to win: their reach is defined by path prefixes, and an IAM policy on a role
 * shared by every external member cannot express them -- there is no `cognito:groups`
 * condition key for identity pool sessions. Granting that role nothing closes the direct
 * path for them and leaves the AppSync path, where the prefixes are enforced, as the only
 * way in. `internal` is last for the mirror-image reason: if it out-ranked a role, every
 * internal member would be selected onto the same role and the role axis would stop
 * meaning anything.
 *
 * Combinations this yields, each checked against how AppSync answers the same question:
 *
 *   contributor + internal     contributor    read + write
 *   viewer + contributor       contributor    read + write (most permissive, as AppSync)
 *   contributor + external     external       no direct S3; AppSync path only
 *   storage-admin + external   external       no direct S3 (the external scope revokes the
 *                                             admin bypass everywhere else too)
 *   internal only              internal       read only
 *   no group                   default role   read only
 */
export const DIRECT_S3_BY_GROUP: DirectS3Grant[] = [
  { group: SCOPE_EXTERNAL, precedence: 0, actions: [] },
  { group: ROLE_STORAGE_ADMIN, precedence: 1, actions: [...S3_READ_ACTIONS, ...S3_WRITE_ACTIONS] },
  { group: ROLE_CONTRIBUTOR, precedence: 2, actions: [...S3_READ_ACTIONS, ...S3_WRITE_ACTIONS] },
  { group: ROLE_VIEWER, precedence: 3, actions: S3_READ_ACTIONS },
  { group: ROLE_AUDITOR, precedence: 4, actions: S3_READ_ACTIONS },
  { group: SCOPE_INTERNAL, precedence: 5, actions: S3_READ_ACTIONS },
];


/**
 * Reasons this mapping and the declared groups disagree. Empty when they match.
 *
 * Both directions matter, and neither surfaces at runtime as itself:
 *
 *   An entry naming a group that is not declared grants nothing, silently.
 *
 *   A declared group with no entry keeps an empty role, and because Cognito selects that
 *   role for its members, they lose S3 entirely. A group added to widen access would
 *   narrow it instead.
 *
 * Two groups sharing a precedence is the third failure, and the worst to diagnose: the
 * docs are explicit that `cognito:preferred_role` is then **not set**, so the identity
 * pool falls back to `AmbiguousRoleResolution` -- the default authenticated role -- and
 * every member of both groups quietly gets the read-only fallback instead of their role.
 *
 * @param declaredGroups Group names from `auth/resource.ts`, in any order.
 */
export function directS3Problems(declaredGroups: readonly string[]): string[] {
  const problems: string[] = [];
  const declared = new Set(declaredGroups);
  for (const { group } of DIRECT_S3_BY_GROUP) {
    if (!declared.has(group)) {
      problems.push(
        `${group} has a DIRECT_S3_BY_GROUP entry but is not declared in auth/resource.ts, ` +
          "so the grant matches nobody"
      );
    }
  }
  for (const group of declaredGroups) {
    if (!DIRECT_S3_BY_GROUP.some((entry) => entry.group === group)) {
      problems.push(
        `${group} is declared in auth/resource.ts but has no DIRECT_S3_BY_GROUP entry, ` +
          "so its members would assume an empty role and lose the Upload tab"
      );
    }
  }
  const seen = new Map<number, string>();
  for (const { group, precedence } of DIRECT_S3_BY_GROUP) {
    const other = seen.get(precedence);
    if (other !== undefined) {
      problems.push(
        `${other} and ${group} share precedence ${precedence}, so cognito:preferred_role ` +
          "is unset for anybody in both and they fall back to the read-only default role"
      );
    }
    seen.set(precedence, group);
  }
  return problems;
}
