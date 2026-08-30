/**
 * What the signed-in account is allowed to do, as the server will answer it.
 *
 * The rules live in AppSync (`amplify/data/resource.ts`) and in the handlers
 * (`shared/portal_external_policy.py`), and they are the only enforcement. This hook
 * exists so the UI stops offering controls the server refuses: without it, a `viewer`
 * saw an upload button, a delete button and a "download folder as ZIP" button, and
 * every one of them returned an authorization error. The refusals were correct; the
 * buttons were the lie.
 *
 * Nothing here is a security control. Hiding a button does not stop a request, and a
 * caller who reconstructs the mutation still meets the same rule. Treat this as
 * labelling.
 *
 * The two halves of the answer come from two places, and neither is guessed:
 *
 *   which groups the caller holds -- the `cognito:groups` claim on the ID token,
 *   already in the session, so asking the backend whether requests are allowed would
 *   cost the round trip it is meant to avoid.
 *
 *   which rules the deployment emitted -- `amplify_outputs.json`, via
 *   `../lib/portalOutputs`. `enforceRoles` is a synth-time choice, so the browser
 *   cannot infer it from the token, and hardcoding one answer here would be wrong in
 *   whichever deployment chose the other.
 *
 * Returns `null` while the session is loading, so a caller can tell "not permitted"
 * from "not known yet" and avoid rendering a control and then withdrawing it.
 */
import { useEffect, useState } from "react";
import { fetchAuthSession } from "aws-amplify/auth";
import {
  PORTAL_ROLES,
  ROLE_AUDITOR,
  ROLE_CONTRIBUTOR,
  ROLE_STORAGE_ADMIN,
  SCOPE_EXTERNAL,
  type PortalRole,
} from "../../amplify/portal-groups";
import {
  enforceRoles,
  externalAiEnabled,
  externalShareLinksByRole,
} from "../lib/portalOutputs";

/** Roles `fileMutation` and `folderMutation` name when `enforceRoles` is on. */
const WRITE_ROLES: readonly string[] = [ROLE_CONTRIBUTOR, ROLE_STORAGE_ADMIN];

/** Roles `queryAuditLog` names when `enforceRoles` is on. */
const AUDIT_ROLES: readonly string[] = [ROLE_AUDITOR, ROLE_STORAGE_ADMIN];

export type PortalCapabilities = {
  /** The portal roles this account holds. Empty when it was added to no group. */
  roles: PortalRole[];
  /** True when the account holds the `external` scope: no Windows or UNIX identity. */
  isExternal: boolean;
  /** True when the account is a `storage-admin`. */
  isAdmin: boolean;
  /**
   * Upload, rename, move, trash, folder creation -- and folder download, because
   * `folderMutation` assembles a ZIP and carries the same rule as the other writes.
   */
  canWrite: boolean;
  /** Read the audit trail and the external-member ledger. */
  canAudit: boolean;
  /**
   * Mint a share link meant to be handed to somebody else: a QR code or an upload link.
   *
   * Preview and download are deliberately not covered. They are the same presigned-URL
   * query, so the server clamps their lifetime instead of refusing them -- see
   * `share_link_expiry_ceiling`. A denied caller still previews and downloads; only the
   * longer lifetimes go away.
   */
  canShareLinks: boolean;
  /** Use the AI endpoints: ask-about-file, semantic search, labels, OCR, agent chat. */
  canUseAi: boolean;
  /**
   * Upload through the Storage Browser, which writes to S3 from the browser directly.
   *
   * A separate answer from `canWrite`, and deliberately not derived from it. That tab
   * does not call AppSync, so `enforceRoles` has no bearing on it: what governs it is
   * the IAM role Cognito selects for the account, which `amplify/backend.ts` grants per
   * group. Writing is granted to `contributor` and `storage-admin`, and the `external`
   * scope takes the direct path away entirely -- an external member's reach is defined
   * by path prefixes, which a role shared by all external members cannot express.
   *
   * The consequence worth stating: with `enforceRoles: false` an ungrouped account may
   * write through AppSync and still cannot upload here.
   */
  canUploadDirect: boolean;
  /**
   * True when the account holds no portal role at all while `enforceRoles` is on.
   *
   * Distinguished from "holds a role that does not permit this" because the fix
   * differs: this account has not been placed in a group yet, and the UI should say so
   * rather than describe it as a permission its role lacks.
   */
  hasNoRole: boolean;
  /** Whether the deployment emits the role-based rules at all. */
  rolesEnforced: boolean;
};

/** Derives the capabilities from a group claim. Exported for tests. */
export function capabilitiesFromGroups(groups: string[]): PortalCapabilities {
  const roles = PORTAL_ROLES.filter((role) => groups.includes(role));
  const isExternal = groups.includes(SCOPE_EXTERNAL);
  const holdsAny = (allowed: readonly string[]) => groups.some((g) => allowed.includes(g));
  // Only the caller's roles are consulted, never every group they hold. Matching any
  // group would make `{"external": true}` in the mapping grant every outside caller at
  // once, cancelling the per-role distinction the setting exists to draw. This mirrors
  // `share_link_denial_reason`, which has to answer the same way.
  const roleAllowsShareLinks = roles.some((role) => externalShareLinksByRole[role] === true);
  return {
    roles: [...roles],
    isExternal,
    isAdmin: groups.includes(ROLE_STORAGE_ADMIN),
    canWrite: !enforceRoles || holdsAny(WRITE_ROLES),
    canAudit: !enforceRoles || holdsAny(AUDIT_ROLES),
    canShareLinks: !isExternal || roleAllowsShareLinks,
    canUseAi: !isExternal || externalAiEnabled,
    // Not gated on `enforceRoles`: this one is IAM, granted per group in `backend.ts`.
    canUploadDirect: !isExternal && holdsAny(WRITE_ROLES),
    hasNoRole: enforceRoles && roles.length === 0,
    rolesEnforced: enforceRoles,
  };
}

export function usePortalRole(): PortalCapabilities | null {
  const [capabilities, setCapabilities] = useState<PortalCapabilities | null>(null);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      let groups: string[] = [];
      try {
        const session = await fetchAuthSession();
        const claim = session.tokens?.idToken?.payload["cognito:groups"];
        // The claim is absent for an account in no group, and a single-element list is
        // still a list, so the shape is checked rather than assumed.
        if (Array.isArray(claim)) {
          groups = claim.filter((entry): entry is string => typeof entry === "string");
        }
      } catch {
        // No readable session means no group claim to honour. Deriving from the empty
        // list is the safe reading: it is what the server would see.
      }
      if (!cancelled) setCapabilities(capabilitiesFromGroups(groups));
    })();
    return () => {
      cancelled = true;
    };
  }, []);
  return capabilities;
}
