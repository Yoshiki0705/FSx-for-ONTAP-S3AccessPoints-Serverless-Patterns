import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage } from "../../lib/portalQuery";
import { adminMutate, adminQuery } from "../../lib/dispatch";

interface Svm {
  name: string;
  /** The FSx identifier (svm-...). The delete goes through the FSx API, which keys
      on this, not the ONTAP UUID. */
  svmId: string;
  state: string;
  subtype: string;
  isDefault: boolean;
}

interface VolumeRef {
  name: string;
  uuid: string;
  junctionPath: string;
}

interface DeletionImpact {
  svm?: string;
  rootVolume: VolumeRef | null;
  nonRootVolumes: VolumeRef[];
  nonRootCount: number;
  canDelete: boolean;
}

/**
 * SVM manager — the widest-blast-radius teardown in the portal.
 *
 * Deleting an SVM removes it with its root volume, so two guards sit in front of
 * the delete:
 *  - the backend refuses while the SVM still owns non-root volumes, and returns the
 *    list of what remains; this panel shows that list from `getSvmDeletionImpact`
 *    before offering the delete at all;
 *  - the operator must re-type the SVM name, so the action cannot happen by clicking
 *    through. This is a dedicated confirm row, not the SnapLock keyword dialog --
 *    that one is reserved for retention locks and its wording would be wrong here.
 */
export function SvmManager() {
  const { t } = useTranslation();
  const [actionError, setActionError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** The SVM whose deletion flow is open, by UUID. */
  const [openFor, setOpenFor] = useState<string | null>(null);
  /** The name the operator has typed to confirm. */
  const [typed, setTyped] = useState("");

  const {
    data: svms = [],
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "listSvms"],
    queryFn: async () => {
      const parsed = await adminQuery<{ svms?: Svm[] }>({ action: "listSvms" });
      if (parsed?.error && !parsed.error.includes("Unknown action") && !parsed.error.includes("not configured")) {
        throw new Error(parsed.error);
      }
      return parsed?.svms ?? [];
    },
  });

  // The impact for the SVM whose flow is open. Keyed by name so switching rows
  // refetches rather than showing the previous SVM's volumes.
  const openSvm = svms.find(s => s.svmId === openFor) ?? null;
  const { data: impact } = useQuery({
    queryKey: ["admin", "getSvmDeletionImpact", openSvm?.name ?? ""],
    enabled: !!openSvm,
    queryFn: async () => {
      const parsed = await adminQuery<DeletionImpact>({
        action: "getSvmDeletionImpact",
        params: { svm: openSvm!.name },
      });
      if (parsed?.error) throw new Error(parsed.error);
      return parsed;
    },
  });

  const loadData = () => void refetch();
  const error = actionError ?? errorMessage(queryError, "Load failed");

  const openFlow = (svm: Svm) => {
    setOpenFor(svm.svmId);
    setTyped("");
    setActionError(null);
  };

  const runDelete = async (svm: Svm) => {
    setBusy(true);
    setActionError(null);
    setSuccess(null);
    try {
      const result = await adminMutate<{ success?: boolean }>({
        action: "deleteSvm",
        params: { svm: svm.name, svmId: svm.svmId, confirm: true },
      });
      if (result?.success) {
        setSuccess(t("svmDeleted").replace("{name}", svm.name));
        setOpenFor(null);
        setTyped("");
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

  return (
    <div className="svm-manager">
      {error && <div className="rm-error">⚠️ {error}</div>}
      {success && <div className="rm-success">✅ {success}</div>}

      <p className="rm-hint">{t("svmIntro")}</p>

      {loading ? (
        <div className="rm-loading">{t("ontapConnecting")}</div>
      ) : svms.length === 0 ? (
        <p className="rm-empty">{t("svmNone")}</p>
      ) : (
        <table className="rm-table">
          <thead><tr><th>{t("svmName")}</th><th>{t("rmState")}</th><th>{t("svmSubtype")}</th><th>{t("rmActions")}</th></tr></thead>
          <tbody>
            {svms.map(svm => (
              <tr key={svm.svmId}>
                <td className="lu-username">
                  {svm.name}
                  {svm.isDefault && <span className="lu-badge" style={{ marginLeft: 6 }}>{t("svmDefault")}</span>}
                </td>
                <td><span className={`lu-badge ${svm.state === "running" ? "active" : "disabled"}`}>{svm.state}</span></td>
                <td>{svm.subtype || "—"}</td>
                <td>
                  {/* The default SVM backs the portal itself; deleting it is never the
                      intent, so the button is withheld rather than guarded. */}
                  {!svm.isDefault && (
                    <button className="rm-btn-danger-sm" disabled={busy} onClick={() => openFlow(svm)}>
                      {t("delete")}
                    </button>
                  )}
                  {openFor === svm.svmId && (
                    <div className="svm-delete-flow" role="alertdialog">
                      {!impact ? (
                        <span className="rm-loading">{t("ontapConnecting")}</span>
                      ) : impact.nonRootCount > 0 ? (
                        <>
                          <p className="sm-confirm-text">
                            {t("svmBlockedByVolumes").replace("{count}", String(impact.nonRootCount))}
                          </p>
                          <ul>
                            {impact.nonRootVolumes.map(v => (
                              <li key={v.uuid}>{v.name}{v.junctionPath ? ` (${v.junctionPath})` : ""}</li>
                            ))}
                          </ul>
                          <button className="rm-btn-sm" onClick={() => setOpenFor(null)}>{t("cancel")}</button>
                        </>
                      ) : (
                        <>
                          <p className="sm-confirm-text">{t("svmConfirmDelete").replace("{name}", svm.name)}</p>
                          <label className="rm-form-row">
                            <span>{t("svmTypeToConfirm").replace("{name}", svm.name)}</span>
                            <input
                              type="text"
                              value={typed}
                              disabled={busy}
                              onChange={e => setTyped(e.target.value)}
                              placeholder={svm.name}
                              autoComplete="off"
                            />
                          </label>
                          <div className="rm-form-actions">
                            <button
                              className="rm-btn-danger-sm"
                              disabled={busy || typed !== svm.name}
                              onClick={() => runDelete(svm)}
                            >
                              {t("rmExecute")}
                            </button>
                            <button className="rm-btn-sm" onClick={() => setOpenFor(null)}>{t("cancel")}</button>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
