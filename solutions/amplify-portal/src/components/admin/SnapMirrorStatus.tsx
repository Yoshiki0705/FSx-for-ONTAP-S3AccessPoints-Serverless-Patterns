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

/** An SVM peer, as the peering listing reports it. */
interface SvmPeer {
  uuid: string;
  state: string;
  applications: string[];
  localSvm: string;
  peerSvm: string;
  peerCluster: string;
}

interface Transfer {
  /** Needed to abort this transfer; the listing did not use to report it. */
  uuid: string;
  state: string;
  bytesTransferred: number;
  endTime: string;
  duration: string;
}

/** Transfer states that are still running, and so can be aborted. */
const ABORTABLE_STATES = new Set(["transferring", "queued", "preparing", "finalizing"]);

/**
 * Relationship states that are on their way somewhere else.
 *
 * Creating a relationship returns as soon as ONTAP accepts the job, so the list
 * refetched right afterwards shows `uninitialized` -- and used to keep showing it
 * until someone reloaded the page, which reads as "the create silently failed".
 */
const TRANSIENT_STATES = new Set(["uninitialized", "transferring", "finalizing", "preparing"]);

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

  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  // Index into `eligiblePeers`, not an SVM name. The peer carries the local SVM, the
  // remote SVM and the remote cluster together, and all three have to agree.
  const [peerIndex, setPeerIndex] = useState(0);
  const [sourceVolume, setSourceVolume] = useState("");
  const [destinationVolume, setDestinationVolume] = useState("");
  const [policy, setPolicy] = useState("MirrorAllSnapshots");
  const [initialize, setInitialize] = useState(true);

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
    // Poll only while something is mid-flight. A relationship that has settled does
    // not need watching, and lag is read from the row's own timestamp anyway.
    refetchInterval: query =>
      (query.state.data ?? []).some(r => TRANSIENT_STATES.has(r.state)) ? 15_000 : false,
  });

  /**
   * The SVM peers a relationship can actually be created over.
   *
   * The destination SVM is not a free choice: it has to be one whose peer with the
   * source cluster is `peered` *and* permits snapmirror. Leaving it implicit meant
   * the create went to the configured default SVM, and the first attempt from this
   * form failed with `SVM peer permission not found.` on a file system that had a
   * working peer -- on a different SVM. Offering the peers instead of an SVM name
   * makes the precondition the control.
   */
  const { data: eligiblePeers = [] } = useQuery({
    queryKey: ["admin", "listSvmPeers", "snapmirror"],
    queryFn: async () => {
      const data = await adminQuery<{ peers?: SvmPeer[] }>({ action: "listSvmPeers" });
      return (data?.peers ?? []).filter(
        p => p.state === "peered" && p.applications?.includes("snapmirror"),
      );
    },
  });
  const peer = eligiblePeers[peerIndex];

  // Mutation handlers report through their own state, so a failed action is
  // never mistaken for a failed load.
  const loadRelationships = () => void refetch();

  /**
   * Refetch now, and again shortly after.
   *
   * ONTAP acknowledges a write before the listing reflects it: deleting a
   * relationship returned success and the row was still there, because the refetch
   * that followed the write raced the change. The second pass is what makes the
   * screen agree with the cluster, and it is cheap enough not to need a condition.
   */
  const reloadAfterWrite = () => {
    loadRelationships();
    setTimeout(loadRelationships, 3000);
  };

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

  /**
   * Stop a transfer that is still running.
   *
   * Separate from `runAction`, which keys its busy state and its success message on
   * the relationship. This one is scoped to a transfer inside an expanded row, and
   * refreshes that row's transfer list rather than the relationship list.
   */
  const abortTransfer = async (relationshipUuid: SnapmirrorUuid, transferUuid: string) => {
    if (!window.confirm(t("smAbortConfirm"))) return;
    setError(null);
    setSuccess(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "abortSnapmirrorTransfer",
        params: { relationshipUuid, transferUuid },
      });
      if (data?.success) {
        setSuccess(t("smAborted"));
        setTimeout(() => setSuccess(null), 4000);
        // Re-read the same row: the aborted transfer's state is what changed.
        const refreshed = await adminQuery<{ transfers?: Transfer[] }>({
          action: "getSnapmirrorTransfers",
          params: { relationshipUuid },
        });
        setTransfers(refreshed?.transfers || []);
      } else {
        setError(data?.error || "Abort failed");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Abort failed");
    }
  };

  /**
   * Create a relationship, provisioning its destination volume here.
   *
   * Separate from `runAction` because there is no relationship yet: nothing to key
   * the busy state on, and no `relationshipUuid` to send. The source lives on
   * another file system, so the only thing this side needs is the remote path.
   */
  const createRelationship = async () => {
    if (!peer) return;
    setCreating(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "createSnapmirror",
        params: {
          // All four come from the one peer, so they cannot disagree.
          svm: peer.localSvm,
          sourcePath: `${peer.peerSvm}:${sourceVolume.trim()}`,
          sourceCluster: peer.peerCluster || undefined,
          destinationVolume: destinationVolume.trim(),
          policy,
          // ONTAP defaults this to false, and every FSx for ONTAP aggregate is
          // FabricPool-attached, so false leaves nowhere to put the destination.
          tieringSupported: true,
          initialize,
        },
      });
      if (data?.success) {
        setSuccess(t("smCreated"));
        setTimeout(() => setSuccess(null), 6000);
        setShowCreate(false);
        setSourceVolume("");
        setDestinationVolume("");
        reloadAfterWrite();
      } else {
        setError(data?.error || "Create failed");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setCreating(false);
    }
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
        reloadAfterWrite();
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

      <div className="lu-toolbar">
        <span className="lu-count">
          {relationships.length} {t("smRelationships")}
        </span>
        <button className="rm-btn-primary" disabled={creating} onClick={() => setShowCreate(v => !v)}>
          + {t("smCreate")}
        </button>
        <button className="rm-btn-sm" onClick={loadRelationships}>
          🔄 {t("refresh")}
        </button>
      </div>

      {/* The prerequisites are on the other cluster, so a failure here reads as a
          portal problem when it is a peering problem. Listed before the form rather
          than surfaced as an error afterwards. */}
      <details className="vs-guide-section" style={{ marginBottom: "1rem" }}>
        <summary>📋 {t("smPrereqTitle")}</summary>
        <ul className="rm-hint">
          <li>{t("smPrereqClusterPeer")}</li>
          <li>{t("smPrereqSvmPeer")}</li>
          <li>{t("smPrereqSource")}</li>
          <li>{t("smPrereqDestination")}</li>
        </ul>
      </details>

      {showCreate && (
        <div className="rm-create-form">
          <h4>{t("smCreate")}</h4>
          <p className="rm-hint" style={{ marginBottom: "0.75rem" }}>{t("smCreateDesc")}</p>
          {/* Without a peer that permits snapmirror there is nothing to choose, and
              the create would fail on the remote cluster rather than here. */}
          {eligiblePeers.length === 0 ? (
            <p className="rm-error">⚠️ {t("smNoEligiblePeer")}</p>
          ) : (
            <>
              <div className="rm-form-row">
                <label htmlFor="sm-peer">{t("smPeer")} *</label>
                <select
                  id="sm-peer"
                  value={peerIndex}
                  onChange={e => setPeerIndex(Number(e.target.value))}
                  disabled={creating}
                >
                  {eligiblePeers.map((p, i) => (
                    <option key={p.uuid} value={i}>
                      {p.peerSvm}
                      {p.peerCluster ? ` (${p.peerCluster})` : ""} → {p.localSvm}
                    </option>
                  ))}
                </select>
              </div>
              <div className="rm-form-row">
                <label htmlFor="sm-source">{t("smSourceVolume")} *</label>
                <input
                  id="sm-source"
                  type="text"
                  value={sourceVolume}
                  onChange={e => setSourceVolume(e.target.value)}
                  placeholder="vol_archive"
                  disabled={creating}
                />
              </div>
              <div className="rm-form-row">
                <label htmlFor="sm-dest">{t("smDestinationVolume")} *</label>
                <input
                  id="sm-dest"
                  type="text"
                  value={destinationVolume}
                  onChange={e => setDestinationVolume(e.target.value)}
                  placeholder="vol_dr_archive"
                  disabled={creating}
                />
              </div>
              <div className="rm-form-row">
                <label htmlFor="sm-policy">{t("smPolicy")}</label>
                <select
                  id="sm-policy"
                  value={policy}
                  onChange={e => setPolicy(e.target.value)}
                  disabled={creating}
                >
                  <option value="MirrorAllSnapshots">MirrorAllSnapshots</option>
                  <option value="MirrorLatest">MirrorLatest</option>
                  <option value="MirrorAndVault">MirrorAndVault</option>
                </select>
              </div>
              <div className="rm-form-row">
                <label htmlFor="sm-init">{t("smInitialize")}</label>
                <input
                  id="sm-init"
                  type="checkbox"
                  checked={initialize}
                  onChange={e => setInitialize(e.target.checked)}
                  disabled={creating}
                />
              </div>
              <p className="rm-hint">
                {peer && (
                  <>
                    {t("smWillCreate")}: <code>{peer.peerSvm}:{sourceVolume || "…"}</code> →{" "}
                    <code>{peer.localSvm}:{destinationVolume || "…"}</code>
                    <br />
                  </>
                )}
                {t("smCreateDestHint")}
              </p>
            </>
          )}
          <div className="rm-form-actions">
            <button
              className="rm-btn-primary"
              disabled={creating || !peer || !sourceVolume.trim() || !destinationVolume.trim()}
              onClick={createRelationship}
            >
              {creating ? t("smCreating") : t("rmCreate")}
            </button>
            <button className="rm-btn-secondary" disabled={creating} onClick={() => setShowCreate(false)}>
              {t("cancel")}
            </button>
          </div>
        </div>
      )}

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
                      <thead><tr><th>{t("rmState")}</th><th>{t("smSize")}</th><th>{t("smEndTime")}</th><th>{t("smDuration")}</th><th>{t("rmActions")}</th></tr></thead>
                      <tbody>{transfers.map((tr, i) => (
                        <tr key={tr.uuid || i}>
                          <td><span className={`lu-badge ${tr.state === "success" ? "active" : ""}`}>{tr.state}</span></td>
                          <td>{formatBytes(tr.bytesTransferred)}</td>
                          <td>{tr.endTime ? new Date(tr.endTime).toLocaleString() : "—"}</td>
                          <td>{tr.duration || "—"}</td>
                          <td>
                            {/* Only while it is still running: aborting a finished
                                transfer is not a thing ONTAP offers. */}
                            {tr.uuid && ABORTABLE_STATES.has(tr.state) ? (
                              <button
                                className="rm-btn-danger-sm"
                                onClick={() => abortTransfer(r.uuid, tr.uuid)}
                                title={t("smAbort")}
                              >
                                ⏹ {t("smAbort")}
                              </button>
                            ) : "—"}
                          </td>
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
