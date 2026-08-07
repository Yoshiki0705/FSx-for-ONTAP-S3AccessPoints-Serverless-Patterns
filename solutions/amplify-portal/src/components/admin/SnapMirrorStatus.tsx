import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage } from "../../lib/portalQuery";
import { adminMutate, adminQuery, type DispatchCall } from "../../lib/dispatch";
import type { SnapmirrorUuid } from "../../lib/dispatchActions";

/** Success message per write action. */
const SUCCESS_KEY = {
  updateSnapmirrorNow: "smUpdateStarted",
  quiesceSnapmirror: "smQuiesced",
  resumeSnapmirror: "smResumed",
  breakSnapmirror: "smBroken",
  resyncSnapmirror: "smResyncStarted",
  deleteSnapmirror: "smDeleted",
} as const;

/** Confirmation prompt per destructive action. */
const CONFIRM_KEY = {
  breakSnapmirror: "smConfirmBreak",
  resyncSnapmirror: "smConfirmResync",
  deleteSnapmirror: "smConfirmDelete",
} as const;

type WriteAction = keyof typeof SUCCESS_KEY;
type ConfirmAction = keyof typeof CONFIRM_KEY;

/**
 * One of the six SnapMirror write calls, with its own parameters.
 *
 * `Extract` narrows the endpoint's whole action union down to these six and keeps
 * each one's parameters attached. That matters because the shapes genuinely differ:
 * break, resync and delete require `confirm`, and update, resume and quiesce do not
 * accept it. A single `(action, uuid, extra: Record<string, unknown>)` signature
 * could not express that, and the compiler said so.
 */
type SnapmirrorCall = Extract<DispatchCall<"adminMutation">, { action: WriteAction }>;

interface SnapMirrorRelationship {
  /**
   * ONTAP's relationship UUID, branded where it arrives.
   *
   * Every write action here identifies the relationship by it, and the source and
   * destination paths sit right beside it in this same object.
   */
  uuid: SnapmirrorUuid;
  sourcePath: string;
  sourceSvm: string;
  destinationPath: string;
  destinationSvm: string;
  state: string;
  healthy: boolean;
  policy: string;
  lagTime: string;
  lastTransferType: string;
}

interface Transfer {
  state: string;
  bytesTransferred: number;
  endTime: string;
  duration: string;
}

export function SnapMirrorStatus() {
  const { t } = useTranslation();
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
  const [expandedUuid, setExpandedUuid] = useState<string | null>(null);
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [transfersLoading, setTransfersLoading] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [busyUuid, setBusyUuid] = useState<string | null>(null);
  // Break, resync and delete redirect or discard data, so they ask first.
  const [confirmFor, setConfirmFor] = useState<{ uuid: string; action: ConfirmAction } | null>(null);

  const {
    data: relationships = [],
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "listSnapmirrorRelationships"],
    queryFn: async () => {
      const data = await adminQuery<{ relationships?: SnapMirrorRelationship[] }>({
        action: "listSnapmirrorRelationships",
      });
      // A dispatcher that has not been wired yet is an empty list, not a failure.
      if (
        data?.error &&
        !data.error.includes("Unknown action") &&
        !data.error.includes("not configured")
      ) {
        throw new Error(data.error);
      }
      return data?.relationships ?? [];
    },
  });

  // Mutation handlers report through their own state, so a failed action is
  // never mistaken for a failed load.
  const loadRelationships = () => void refetch();
  const error = actionError ?? errorMessage(queryError, "Failed to load relationships");


  const toggleTransfers = async (uuid: SnapmirrorUuid) => {
    if (expandedUuid === uuid) { setExpandedUuid(null); return; }
    setExpandedUuid(uuid);
    setTransfersLoading(true);
    try {
      const data = await adminQuery<{ transfers?: Transfer[] }>({
        action: "getSnapmirrorTransfers",
        params: { relationshipUuid: uuid },
      });
      setTransfers(data?.transfers || []);
    } catch { setTransfers([]); }
    finally { setTransfersLoading(false); }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "—";
    if (bytes < 1024**2) return `${Math.round(bytes / 1024)} KB`;
    if (bytes < 1024**3) return `${(bytes / 1024**2).toFixed(1)} MB`;
    return `${(bytes / 1024**3).toFixed(2)} GB`;
  };

  /** Run a write action, then refresh the list. */
  const runAction = async (call: SnapmirrorCall) => {
    setBusyUuid(call.params.relationshipUuid);
    setError(null);
    setSuccess(null);
    try {
      const data = await adminMutate<{ success?: boolean }>(call);
      if (data?.success) {
        setSuccess(t(SUCCESS_KEY[call.action]));
        setTimeout(() => setSuccess(null), 4000);
        loadRelationships();
      } else {
        setError(data?.error || "Action failed");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusyUuid(null);
      setConfirmFor(null);
    }
  };

  return (
    <div className="snapmirror-status">
      {error && <div className="rm-error">⚠️ {error}</div>}
      {success && <div className="rm-success">✅ {success}</div>}

      {loading ? <div className="rm-loading">{t("ontapConnecting")}</div> : relationships.length === 0 ? (
        <p className="rm-empty">{t("smNoRelationships")}</p>
      ) : (
        <div className="lu-groups-list">
          {relationships.map(r => (
            <div key={r.uuid} className="lu-group-card">
              <div className="lu-group-header">
                <div className="lu-group-info">
                  <span className="lu-group-name">{r.sourcePath} → {r.destinationPath}</span>
                  <span className="lu-group-desc">
                    {t("smPolicy")}: {r.policy} | Lag: {r.lagTime || "—"}
                  </span>
                </div>
                <div className="lu-group-actions">
                  <span className={`lu-badge ${r.healthy ? "active" : "disabled"}`}>
                    {r.healthy ? t("smHealthy") : t("smUnhealthy")}
                  </span>
                  <span className="lu-badge">{r.state}</span>
                  <button className="rm-btn-sm" onClick={() => toggleTransfers(r.uuid)}>
                    {expandedUuid === r.uuid ? "▼" : "▶"} {t("smTransfers")}
                  </button>
                </div>
              </div>

              <div className="sm-actions">
                <button
                  className="rm-btn-sm"
                  disabled={busyUuid === r.uuid}
                  onClick={() =>
                    runAction({ action: "updateSnapmirrorNow", params: { relationshipUuid: r.uuid } })
                  }
                >
                  ⟳ {t("smUpdateNow")}
                </button>
                {r.state === "paused" ? (
                  <button
                    className="rm-btn-sm"
                    disabled={busyUuid === r.uuid}
                    onClick={() =>
                      runAction({ action: "resumeSnapmirror", params: { relationshipUuid: r.uuid } })
                    }
                  >
                    ▶ {t("smResume")}
                  </button>
                ) : (
                  <button
                    className="rm-btn-sm"
                    disabled={busyUuid === r.uuid}
                    onClick={() =>
                      runAction({ action: "quiesceSnapmirror", params: { relationshipUuid: r.uuid } })
                    }
                  >
                    ⏸ {t("smQuiesce")}
                  </button>
                )}
                {r.state === "broken_off" ? (
                  <button
                    className="rm-btn-sm"
                    disabled={busyUuid === r.uuid}
                    onClick={() => setConfirmFor({ uuid: r.uuid, action: "resyncSnapmirror" })}
                  >
                    ⇄ {t("smResync")}
                  </button>
                ) : (
                  <button
                    className="rm-btn-danger-sm"
                    disabled={busyUuid === r.uuid}
                    onClick={() => setConfirmFor({ uuid: r.uuid, action: "breakSnapmirror" })}
                  >
                    ✂ {t("smBreak")}
                  </button>
                )}
                <button
                  className="rm-btn-danger-sm"
                  disabled={busyUuid === r.uuid}
                  onClick={() => setConfirmFor({ uuid: r.uuid, action: "deleteSnapmirror" })}
                >
                  {t("smDelete")}
                </button>
              </div>

              {confirmFor?.uuid === r.uuid && (
                <div className="sm-confirm" role="alertdialog">
                  <span className="sm-confirm-text">{t(CONFIRM_KEY[confirmFor.action])}</span>
                  <button
                    className="rm-btn-danger-sm"
                    disabled={busyUuid === r.uuid}
                    onClick={() =>
                      // The three destructive actions all require `confirm`, which is
                      // why they share this one confirmation path.
                      runAction({
                        action: confirmFor.action,
                        params: { relationshipUuid: r.uuid, confirm: true },
                      })
                    }
                  >
                    {t("rmExecute")}
                  </button>
                  <button className="rm-btn-secondary" onClick={() => setConfirmFor(null)}>
                    {t("cancel")}
                  </button>
                </div>
              )}

              {expandedUuid === r.uuid && (
                <div className="lu-members-panel">
                  {transfersLoading ? <p className="rm-loading-sm">...</p> : transfers.length === 0 ? (
                    <p className="rm-empty-sm">{t("smNoTransfers")}</p>
                  ) : (
                    <table className="rm-table" style={{ fontSize: "0.85rem" }}>
                      <thead><tr><th>{t("rmState")}</th><th>{t("smSize")}</th><th>{t("smEndTime")}</th><th>{t("smDuration")}</th></tr></thead>
                      <tbody>{transfers.map((tr, i) => (
                        <tr key={i}>
                          <td><span className={`lu-badge ${tr.state === "success" ? "active" : ""}`}>{tr.state}</span></td>
                          <td>{formatBytes(tr.bytesTransferred)}</td>
                          <td>{tr.endTime ? new Date(tr.endTime).toLocaleString() : "—"}</td>
                          <td>{tr.duration || "—"}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
