/**
 * Tells the account what it is allowed to do, and why.
 *
 * Hiding a control the server refuses stops the error, but it also removes the only
 * evidence that anything was refused: an account with no role saw a file listing with
 * no upload button and nothing to say the button was missing rather than absent from
 * the product. That reading is worse than the error was, because there is no message
 * to search for and no setting named.
 *
 * So each hidden capability gets a sentence naming what is missing and who can grant
 * it, and the topbar carries the role and scope so the answer is on screen before the
 * question is asked.
 *
 * Not a security boundary. `amplify/data/resource.ts` and the handlers decide; this
 * describes their decision.
 */
import { useTranslation } from "../i18n";
import { usePortalRole, type PortalCapabilities } from "../hooks/usePortalRole";

/**
 * A refusal explained: what is unavailable, and which setting or group changes it.
 *
 * Reuses the `agent-disabled` styling that the AI-off and admin-only notices already
 * use, so the three read as one kind of message rather than three.
 */
export function RoleNotice({ title, description }: { title: string; description: string }) {
  return (
    <div className="agent-disabled">
      <div className="agent-disabled-icon">🔒</div>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

/** The audit trail is not readable by this role. */
export function AuditDenied() {
  const { t } = useTranslation();
  return <RoleNotice title={t("roleAuditDeniedTitle")} description={t("roleAuditDeniedDesc")} />;
}

/**
 * The Storage Browser's direct path to S3 is not open to this account.
 *
 * Two wordings again, and here the difference is not about which role to ask for. An
 * external member is not missing a grant somebody forgot: the direct path cannot express
 * their path prefixes, so it is closed by design and the way in is the upload link. A
 * read-only internal account, by contrast, needs `contributor`.
 */
export function DirectUploadDenied({ external }: { external: boolean }) {
  const { t } = useTranslation();
  return (
    <RoleNotice
      title={external ? t("roleExternalUploadTitle") : t("roleDirectUploadTitle")}
      description={external ? t("roleExternalUploadDesc") : t("roleDirectUploadDesc")}
    />
  );
}

/** The AI endpoints are closed to external callers in this deployment. */
export function ExternalAiDenied() {
  const { t } = useTranslation();
  return <RoleNotice title={t("roleExternalAiTitle")} description={t("roleExternalAiDesc")} />;
}

/**
 * Read-only banner for the file explorer.
 *
 * Two wordings, because the fix differs. An account holding `viewer` has a role that
 * does not include writes; an account holding no role has not been placed in a group
 * yet, and telling that person their role lacks a permission would send them looking
 * for a role they do not have.
 */
export function ReadOnlyBanner({ capabilities }: { capabilities: PortalCapabilities }) {
  const { t } = useTranslation();
  return (
    <div className="role-readonly-banner" role="status">
      <span className="role-readonly-icon" aria-hidden="true">
        👁️
      </span>
      <div>
        <strong>{t("roleReadOnlyTitle")}</strong>
        <p>
          {capabilities.hasNoRole ? t("roleReadOnlyNoRoleDesc") : t("roleReadOnlyDesc")}
        </p>
      </div>
    </div>
  );
}

/**
 * The account's role and scope, in the topbar.
 *
 * Renders nothing while the session is loading, and nothing for an internal account
 * holding a role -- the ordinary case, where a badge would be noise. It appears when
 * something about the account limits it: no role, or the external scope.
 */
export function RoleBadge() {
  const { t } = useTranslation();
  const capabilities = usePortalRole();
  if (capabilities === null) return null;
  const { roles, isExternal, hasNoRole } = capabilities;
  if (!isExternal && !hasNoRole) return null;
  return (
    <span className="role-badge-group">
      {hasNoRole ? (
        <span className="role-badge role-badge-warn" title={t("roleBadgeNoRoleTitle")}>
          {t("roleBadgeNoRole")}
        </span>
      ) : (
        // Role names are Cognito group names and are not translated: an administrator
        // reading this over somebody's shoulder has to match it against the group list.
        roles.map((role) => (
          <span className="role-badge" key={role} title={t("roleBadgeRoleTitle")}>
            {role}
          </span>
        ))
      )}
      {isExternal && (
        <span className="role-badge role-badge-external" title={t("roleBadgeExternalTitle")}>
          {t("roleBadgeExternal")}
        </span>
      )}
    </span>
  );
}
