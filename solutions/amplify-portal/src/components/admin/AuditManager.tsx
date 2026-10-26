import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage } from "../../lib/portalQuery";
import { adminMutate, adminQuery, type DispatchCall } from "../../lib/dispatch";

interface AuditLeg {
  enabled: boolean;
  logVolume: string;
  configured: boolean;
}

interface AuditConfig {
  svm?: string;
  nasAudit: AuditLeg | null;
  objectStoreAudit: AuditLeg | null;
}

/**
 * Audit manager — view and remove an SVM's NAS and object-store audit
 * configuration.
 *
 * The reason to expose this in a teardown context: a volume that is an audit log
 * destination cannot be deleted while it holds that role. The panel shows which
 * volume each audit leg writes to (the dependency a volume delete has to clear)
 * and lets the operator remove the configuration. Removal is inline-confirmed, the
 * way the other teardown deletes in this portal are; it is not routed through the
 * retention-lock dialog, which is reserved for SnapLock and snapshot locking.
 */
export function AuditManager() {
  const { t } = useTranslation();
  const [actionError, setActionError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** Which leg is awaiting delete confirmation. */
  const [confirmFor, setConfirmFor] = useState<"nas" | "objectStore" | null>(null);

  const {
    data,
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "getAuditConfig"],
    queryFn: async () => {
      const parsed = await adminQuery<AuditConfig>({ action: "getAuditConfig" });
      if (parsed?.error && !parsed.error.includes("Unknown action") && !parsed.error.includes("not configured")) {
        throw new Error(parsed.error);
      }
      return parsed;
    },
  });

  const loadData = () => void refetch();
  const error = actionError ?? errorMessage(queryError, "Load failed");

  // Takes the whole call with a literal action, rather than computing the action
  // name from the leg. The action-parameter contract check reads literal call sites
  // only; a computed name is invisible to it, which is how a mis-wired delete button
  // has shipped elsewhere in this portal.
  const runDelete = async (call: DispatchCall<"adminMutation">) => {
    setBusy(true);
    setActionError(null);
    setSuccess(null);
    try {
      const result = await adminMutate<{ success?: boolean }>(call);
      if (result?.success) {
        setSuccess(t("auditDeleted"));
        setConfirmFor(null);
        setTimeout(() => setSuccess(null), 4000);
        loadData();
      } else {
        setActionError(result?.error || "Delete failed");
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  const renderLeg = (leg: "nas" | "objectStore", config: AuditLeg | null, label: string) => {
    if (!config || !config.configured) {
      return (
        <div className="rm-form" key={leg}>
          <h4>{label}</h4>
          <p className="rm-empty">{t("auditNotConfigured")}</p>
        </div>
      );
    }
    return (
      <div className="rm-form" key={leg}>
        <h4>{label}</h4>
        <table className="rm-table">
          <tbody>
            <tr>
              <td>{t("auditEnabled")}</td>
              <td>
                <span className={`lu-badge ${config.enabled ? "active" : "disabled"}`}>
                  {config.enabled ? t("luActive") : t("luDisabled")}
                </span>
              </td>
            </tr>
            <tr>
              <td>{t("auditLogVolume")}</td>
              <td className="lu-username">{config.logVolume || "—"}</td>
            </tr>
          </tbody>
        </table>
        {/* The dependency this panel exists to surface: the log volume cannot be
            deleted until this audit configuration is removed. */}
        {config.logVolume && <p className="rm-hint">{t("auditVolumeDependencyHint")}</p>}
        <div className="rm-form-actions">
          <button className="rm-btn-danger-sm" disabled={busy} onClick={() => setConfirmFor(leg)}>
            {t("auditDelete")}
          </button>
        </div>
        {confirmFor === leg && (
          <span className="peer-accept-row" role="alertdialog">
            <span className="sm-confirm-text">{t("auditConfirmDelete")}</span>
            <button
              className="rm-btn-danger-sm"
              disabled={busy}
              onClick={() =>
                runDelete(
                  leg === "nas"
                    ? { action: "deleteAudit", params: { confirm: true } }
                    : { action: "deleteObjectStoreAudit", params: { confirm: true } },
                )
              }
            >
              {t("rmExecute")}
            </button>
            <button className="rm-btn-sm" onClick={() => setConfirmFor(null)}>
              {t("cancel")}
            </button>
          </span>
        )}
      </div>
    );
  };

  return (
    <div className="audit-manager">
      {error && <div className="rm-error">⚠️ {error}</div>}
      {success && <div className="rm-success">✅ {success}</div>}

      <p className="rm-hint">{t("auditIntro")}</p>

      {loading ? (
        <div className="rm-loading">{t("ontapConnecting")}</div>
      ) : (
        <>
          {renderLeg("nas", data?.nasAudit ?? null, t("auditNas"))}
          {renderLeg("objectStore", data?.objectStoreAudit ?? null, t("auditObjectStore"))}
        </>
      )}
    </div>
  );
}
