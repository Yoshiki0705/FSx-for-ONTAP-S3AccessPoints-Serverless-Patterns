import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";

const client = generateClient<Schema>();

function parseResponse<T>(response: { data?: string | null }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === "string" ? JSON.parse(response.data) : response.data;
  } catch { return null; }
}

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

interface SnapMirrorRelationship {
  uuid: string;
  sourcePath: string;
  sourceSvm: string;
  destinationPath: string;
  destinationSvm: string;
  state: string;
  healthy: boolean;
  policy: string;
  lagTime: string;
  lastTransferType: string;
  lastTransferSize: number;
}

interface Transfer {
  state: string;
  bytesTransferred: number;
  endTime: string;
  duration: string;
}

export function SnapMirrorStatus() {
  const { t } = useTranslation();
  const [relationships, setRelationships] = useState<SnapMirrorRelationship[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedUuid, setExpandedUuid] = useState<string | null>(null);
  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [transfersLoading, setTransfersLoading] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [busyUuid, setBusyUuid] = useState<string | null>(null);
  // Break, resync and delete redirect or discard data, so they ask first.
  const [confirmFor, setConfirmFor] = useState<{ uuid: string; action: ConfirmAction } | null>(null);

  const loadRelationships = async () => {
    setLoading(true); setError(null);
    try {
      const resp = await (client.queries as any).adminQuery({ action: "listSnapmirrorRelationships", params: JSON.stringify({}) });
      const data = parseResponse<{ relationships?: SnapMirrorRelationship[]; error?: string }>(resp);
      if (data?.error && !data.error.includes("Unknown action") && !data.error.includes("not configured")) {
        setError(data.error);
      } else {
        setRelationships(data?.relationships || []);
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Load failed"); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadRelationships(); }, []);

  const toggleTransfers = async (uuid: string) => {
    if (expandedUuid === uuid) { setExpandedUuid(null); return; }
    setExpandedUuid(uuid);
    setTransfersLoading(true);
    try {
      const resp = await (client.queries as any).adminQuery({
        action: "getSnapmirrorTransfers", params: JSON.stringify({ relationshipUuid: uuid }),
      });
      const data = parseResponse<{ transfers?: Transfer[]; error?: string }>(resp);
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
  const runAction = async (
    action: WriteAction,
    uuid: string,
    extra: Record<string, unknown> = {}
  ) => {
    setBusyUuid(uuid);
    setError(null);
    setSuccess(null);
    try {
      const resp = await (client.mutations as any).adminMutation({
        action,
        params: JSON.stringify({ relationshipUuid: uuid, ...extra }),
      });
      const data = parseResponse<{ success?: boolean; error?: string }>(resp);
      if (data?.success) {
        setSuccess(t(SUCCESS_KEY[action]));
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
                  onClick={() => runAction("updateSnapmirrorNow", r.uuid)}
                >
                  ⟳ {t("smUpdateNow")}
                </button>
                {r.state === "paused" ? (
                  <button
                    className="rm-btn-sm"
                    disabled={busyUuid === r.uuid}
                    onClick={() => runAction("resumeSnapmirror", r.uuid)}
                  >
                    ▶ {t("smResume")}
                  </button>
                ) : (
                  <button
                    className="rm-btn-sm"
                    disabled={busyUuid === r.uuid}
                    onClick={() => runAction("quiesceSnapmirror", r.uuid)}
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
                    onClick={() => runAction(confirmFor.action, r.uuid, { confirm: true })}
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
