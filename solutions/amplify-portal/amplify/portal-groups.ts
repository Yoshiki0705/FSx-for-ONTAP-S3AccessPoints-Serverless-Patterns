/**
 * The Cognito group names the portal's authorization is expressed in.
 *
 * Two axes, deliberately independent, because they are enforced in different places
 * and a single combined axis would have to be enforced in both:
 *
 *   role   decides which operations a caller may invoke, at the AppSync layer
 *   scope  decides which data a caller reaches, through the access point and the
 *          path prefixes
 *
 * A caller holds one role and one scope. Combining them into six product groups
 * would multiply the names without adding expressiveness, and `cognito:groups` is an
 * array, so holding one of each is the natural encoding.
 *
 * Declared here rather than inline because four files need the same strings:
 * `auth/resource.ts` creates the groups, `data/resource.ts` guards operations with
 * them, `backend.ts` validates the configuration against them, and the Python
 * boundary in `shared/portal_path_scope.py` reads two of them at runtime. The last
 * one cannot import this file, so `tests/infrastructure/backend-assertions.test.ts`
 * asserts the two sides still agree -- a group renamed on one side only would leave
 * the boundary looking configured while matching nobody.
 */

/** Read and download only. */
export const ROLE_VIEWER = "viewer";

/** Adds writes: upload, rename, move, trash, folder creation. */
export const ROLE_CONTRIBUTOR = "contributor";

/**
 * Adds ONTAP configuration and the analytics console.
 *
 * Pre-existing, and the only role that was ever declared. Membership is already
 * granted in deployed user pools, so its name must not change.
 */
export const ROLE_STORAGE_ADMIN = "storage-admin";

/**
 * Reads the audit trail. Not a superset of `viewer` and not a subset either.
 *
 * An auditor needs to see who did what and must not be able to change it, so the
 * role is orthogonal to the read/write ladder rather than a rung on it. That is why
 * `queryAuditLog` names `auditor` and `storage-admin` and does not name `viewer`.
 */
export const ROLE_AUDITOR = "auditor";

/** Inside the organisation. Eligible for the path-boundary bypass when also an admin. */
export const SCOPE_INTERNAL = "internal";

/**
 * Outside the organisation: a member with no Windows or UNIX account on the file
 * system, identified only by an email address.
 *
 * Holding this scope is what confines a caller even when the caller is also a
 * `storage-admin`, and what denies the AI endpoints by default.
 */
export const SCOPE_EXTERNAL = "external";

export const PORTAL_ROLES = [
  ROLE_VIEWER,
  ROLE_CONTRIBUTOR,
  ROLE_STORAGE_ADMIN,
  ROLE_AUDITOR,
] as const;

export const PORTAL_SCOPES = [SCOPE_INTERNAL, SCOPE_EXTERNAL] as const;

/**
 * Every group the portal declares.
 *
 * `storage-admin` stays first so the diff against the previous single-group
 * declaration reads as an addition rather than a rewrite.
 */
export const ALL_PORTAL_GROUPS = [
  ROLE_STORAGE_ADMIN,
  ROLE_VIEWER,
  ROLE_CONTRIBUTOR,
  ROLE_AUDITOR,
  SCOPE_INTERNAL,
  SCOPE_EXTERNAL,
] as const;

export type PortalRole = (typeof PORTAL_ROLES)[number];
export type PortalScope = (typeof PORTAL_SCOPES)[number];
