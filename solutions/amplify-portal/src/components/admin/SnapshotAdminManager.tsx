import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage, unwrap } from "../../lib/portalQuery";
import { adminMutate, dispatch } from "../../lib/dispatch";
import type { PolicyUuid, VolumeUuid } from "../../lib/dispatchActions";
import { SnaplockConfirmDialog } from "../SnaplockConfirmDialog";
import { VolumeSelector } from "./VolumeSelector";
import {
  isZeroPeriod,
  parseIsoPeriod,
  type SnaplockIntent,
} from "../../utils/snaplockConsequences";

// The typed keyword now lives with the confirmation dialog, as
// SNAPLOCK_CONFIRM_KEYWORD, so that every irreversible SnapLock action asks for
// the same word instead of each panel choosing its own.

// Parse the JSON string response from generic dispatch endpoints

interface SnapshotPolicy {
  name: string;
  /** Branded where it arrives, so the delete cannot be handed a policy name. */
  uuid: PolicyUuid;
  enabled: boolean;
  comment: string;
  scheduleCount: number;
  schedules: { schedule: string; count: number; prefix: string; retentionPeriod: string }[];
}

/**
 * Policies ONTAP ships and will not delete.
 *
 * They appear in the listing next to the ones an operator created, and offering a
 * delete on them would only ever return an error from the cluster.
 */
const BUILTIN_POLICIES = new Set(["default", "default-1weekly", "none"]);

interface LockingConfig {
  volumeName: string;
  snapshotLockingEnabled: boolean;
  snapshotPolicy: string;
  lockedSnapshotCount: number;
  totalSnapshotCount: number;
}

/**
 * Snapshot Administration — Policy management, Tamperproof locking, Schedule config.
 *
 * System Manager equivalent: Storage > Volumes > Snapshot Policies + Tamperproof
 *
 * Features:
 * - List/create snapshot policies (with schedules + retention periods)
 * - Enable tamperproof snapshot locking per volume
 * - Lock individual snapshots with retention (cannot delete until expiry)
 * - Assign policies to volumes
 * - View locking status per volume
 */
export function SnapshotAdminManager() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<"policies" | "tamperproof">("policies");
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
  const [result, setResult] = useState<string | null>(null);
  /** Set while the consequence dialog is open; null when nothing is pending. */
  const [pendingSnaplock, setPendingSnaplock] = useState<SnaplockIntent | null>(null);
  const [showCreatePolicy, setShowCreatePolicy] = useState(false);
  /** Policy awaiting delete confirmation, by UUID. */
  const [confirmDeleteUuid, setConfirmDeleteUuid] = useState<string | null>(null);
  // Null until a volume is picked, rather than an empty string: the actions below
  // take a branded UUID, and "" is not one. The selector supplies the branded value.
  const [volumeUuid, setVolumeUuid] = useState<VolumeUuid | null>(null);

  // Policy form state
  const [policyName, setPolicyName] = useState("");
  const [policyComment, setPolicyComment] = useState("");
  const [policySchedule, setPolicySchedule] = useState("daily");
  const [policyCount, setPolicyCount] = useState(7);
  const [policyRetention, setPolicyRetention] = useState("");

  const clearResult = () => setTimeout(() => setResult(null), 4000);

  const policiesQuery = useQuery({
    queryKey: ["admin", "listSnapshotPolicies"],
    enabled: activeTab === "policies",
    queryFn: () =>
      unwrap<{ policies?: SnapshotPolicy[] }>(
        dispatch("adminQuery", { action: "listSnapshotPolicies" }),
      ).then((d) => d?.policies ?? []),
  });

  // Locking status is per volume, so the selected volume is part of the key.
  const lockQuery = useQuery({
    queryKey: ["admin", "getSnapshotLockingStatus", volumeUuid],
    enabled: !!volumeUuid,
    queryFn: () => {
      // `enabled` keeps this from running without a volume, but that is a runtime
      // guarantee the type cannot see, so the narrowing is written out.
      if (!volumeUuid) return Promise.resolve(null);
      return unwrap<{ config?: LockingConfig }>(
        dispatch("adminQuery", {
          action: "getSnapshotLockingStatus",
          params: { volumeUuid },
        }),
      ).then((d) => d?.config ?? null);
    },
  });

  const policies = policiesQuery.data ?? [];
  const lockConfig = lockQuery.data ?? null;
  const loading = policiesQuery.isFetching || lockQuery.isFetching;

  // Mutation handlers report through their own state, so a failed action is
  // never mistaken for a failed load.
  const loadPolicies = () => void policiesQuery.refetch();
  const loadLockingStatus = () => void lockQuery.refetch();
  const error =
    actionError ??
    errorMessage(policiesQuery.error ?? lockQuery.error, t("rmLoadFailed"));

  /**
   * A retention period on a policy is the recurring form of a snapshot lock:
   * every snapshot the schedule takes is locked, without anyone present to
   * approve each one. The field is free text, so it is validated here first —
   * previously `P99Y` was accepted silently and would have locked every
   * snapshot for a century.
   *
   * With no retention this is an ordinary policy, so it submits directly rather
   * than asking about consequences it does not have.
   */
  const handleCreatePolicyClick = () => {
    if (!policyName) { setError(t("rmSnapPolicyNameRequired")); return; }

    const trimmed = policyRetention.trim();
    if (!trimmed) { setError(null); void handleCreatePolicy(); return; }

    const period = parseIsoPeriod(trimmed);
    if (!period) { setError(t("rmSnapRetentionInvalid")); return; }
    if (isZeroPeriod(period)) { setError(null); void handleCreatePolicy(); return; }

    setError(null);
    setPendingSnaplock({
      kind: "snapshotPolicyRetention",
      policyName,
      retentionPeriod: trimmed,
      schedule: policySchedule,
      count: policyCount,
    });
  };

  const handleCreatePolicy = async () => {
    if (!policyName) { setError(t("rmSnapPolicyNameRequired")); return; }
    try {
      const retention = policyRetention.trim();
      const data = await adminMutate<{ success?: boolean }>({
        action: "createSnapshotPolicy",
        params: {
          name: policyName,
          comment: policyComment,
          // The schedules travel as a JSON string because that is what the handler
          // parses, which puts `retentionPeriod` out of reach of the branded type.
          // `handleCreatePolicyClick` validates it with `parseIsoPeriod` before this
          // runs, so the check happens — just one layer up rather than in the type.
          schedules: JSON.stringify([
            { schedule: policySchedule, count: policyCount, retentionPeriod: retention || undefined },
          ]),
          // Only sent when a retention period makes the policy lock snapshots;
          // the backend refuses that combination without it.
          ...(retention ? { acknowledgeIrreversible: true as const } : {}),
        },
      });
      if (data) {
        if (data.success) {
          setResult(`${t("rmSnapPolicyCreated")}: ${policyName}`); clearResult();
          setShowCreatePolicy(false); setPolicyName(""); setPolicyComment("");
          loadPolicies();
        } else setError(data.error || t("rmActionFailed"));
      }
    } catch (err) { setError(err instanceof Error ? err.message : t("rmActionFailed")); }
  };

  /**
   * Delete a policy.
   *
   * Not guarded by the consequence dialog: deleting a policy stops future snapshots
   * and touches neither the snapshots already taken nor any lock on them, so there
   * is nothing irreversible to acknowledge. ONTAP refuses the delete while a volume
   * still references the policy, and that refusal is surfaced as-is.
   */
  const handleDeletePolicy = async (policyUuid: PolicyUuid) => {
    setError(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "deleteSnapshotPolicy",
        params: { policyUuid, confirm: true },
      });
      if (data?.success) {
        setResult(t("rmSnapPolicyDeleted"));
        clearResult();
        loadPolicies();
      } else {
        setError(data?.error || t("rmActionFailed"));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("rmActionFailed"));
    } finally {
      setConfirmDeleteUuid(null);
    }
  };

  /**
   * Enabling locking cannot be undone, so it goes through the consequence
   * dialog. That replaces a `window.prompt` which asked for a keyword but could
   * not show what enabling actually does, and which the browser renders as a
   * bare unstyled box with no room for the explanation.
   */
  const handleEnableLockingClick = () => {
    if (!volumeUuid) return;
    setError(null);
    setPendingSnaplock({
      kind: "enableSnapshotLocking",
      volumeName: lockConfig?.volumeName || volumeUuid,
    });
  };

  const handleEnableLocking = async () => {
    if (!volumeUuid) return;
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "enableSnapshotLocking",
        params: { volumeUuid, enabled: true, acknowledgeIrreversible: true },
      });
      if (data) {
        if (data.success) { setResult(t("rmSnapLockingEnabled")); clearResult(); loadLockingStatus(); }
        else setError(data.error || t("rmActionFailed"));
      }
    } catch (err) { setError(err instanceof Error ? err.message : t("rmActionFailed")); }
  };

  if (loading && activeTab === "policies" && policies.length === 0) return <p className="loading">{t("loading")}</p>;

  return (
    <div className="admin-panel">
      {pendingSnaplock && (
        <SnaplockConfirmDialog
          intent={pendingSnaplock}
          onCancel={() => setPendingSnaplock(null)}
          onConfirm={() => {
            const intent = pendingSnaplock;
            setPendingSnaplock(null);
            // This panel raises two different intents, so the confirmation has
            // to dispatch rather than assume which one is pending.
            if (intent.kind === "snapshotPolicyRetention") void handleCreatePolicy();
            else void handleEnableLocking();
          }}
        />
      )}
      <div className="panel-header">
        <h3>{t("rmSnapshotAdmin")}</h3>
        <div className="panel-actions">
          <button onClick={() => setActiveTab("policies")} className={activeTab === "policies" ? "btn-primary" : "btn-secondary"}>
            {t("rmSnapPolicies")}
          </button>
          <button onClick={() => setActiveTab("tamperproof")} className={activeTab === "tamperproof" ? "btn-primary" : "btn-secondary"}>
            {t("rmSnapTamperproof")}
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}
      {result && <div className="success-message">{result}</div>}

      {activeTab === "policies" && (
        <>
          <div className="panel-actions" style={{ marginBottom: "1rem" }}>
            <button onClick={() => setShowCreatePolicy(!showCreatePolicy)} className="btn-primary">
              + {t("rmSnapCreatePolicy")}
            </button>
            <button onClick={loadPolicies} className="refresh-btn">↻</button>
          </div>

          {showCreatePolicy && (
            <div className="create-form">
              <div className="form-row">
                <div className="form-group">
                  <label>{t("rmSnapPolicyName")}</label>
                  <input type="text" value={policyName} onChange={(e) => setPolicyName(e.target.value)} placeholder="my_policy" />
                </div>
                <div className="form-group">
                  <label>{t("rmSnapSchedule")}</label>
                  <select value={policySchedule} onChange={(e) => setPolicySchedule(e.target.value)}>
                    <option value="5min">5min</option>
                    <option value="8hour">8hour</option>
                    <option value="hourly">Hourly</option>
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>{t("rmSnapCount")}</label>
                  <input type="number" value={policyCount} onChange={(e) => setPolicyCount(parseInt(e.target.value))} min={1} max={1023} />
                </div>
                <div className="form-group">
                  <label>{t("rmSnapRetention")} (ISO)</label>
                  <input type="text" value={policyRetention} onChange={(e) => setPolicyRetention(e.target.value)} placeholder="P30D (optional)" />
                  <small>{t("rmSnapRetentionHint")}</small>
                </div>
              </div>
              <div className="form-group">
                <label>{t("rmShareComment")}</label>
                <input type="text" value={policyComment} onChange={(e) => setPolicyComment(e.target.value)} placeholder={t("labelOptional")} />
              </div>
              <button onClick={handleCreatePolicyClick} className="btn-primary">{t("rmCreate")}</button>
              <button onClick={() => setShowCreatePolicy(false)} className="btn-secondary">{t("cancel")}</button>
            </div>
          )}

          <table className="admin-table">
            <thead><tr><th>{t("rmSnapPolicyName")}</th><th>{t("rmSnapSchedules")}</th><th>{t("rmState")}</th><th>{t("rmShareComment")}</th><th>{t("rmActions")}</th></tr></thead>
            <tbody>
              {policies.map((p) => (
                <tr key={p.uuid}>
                  <td>{p.name}</td>
                  <td>
                    {p.schedules.map((s, i) => (
                      <div key={i}>
                        <code>{s.schedule}</code> × {s.count}
                        {s.retentionPeriod && <span className="badge"> 🔒 {s.retentionPeriod}</span>}
                      </div>
                    ))}
                  </td>
                  <td><span className={`state-badge state-${p.enabled ? "online" : "offline"}`}>{p.enabled ? t("stateEnabled") : t("stateDisabled")}</span></td>
                  <td>{p.comment || "—"}</td>
                  <td>
                    {/* The built-in policies are cluster-scoped and ONTAP refuses to
                        delete them, so offering the button on those rows would only
                        produce an error. */}
                    {BUILTIN_POLICIES.has(p.name) ? (
                      <span className="rm-hint">{t("rmSnapPolicyBuiltin")}</span>
                    ) : confirmDeleteUuid === p.uuid ? (
                      <span className="peer-accept-row">
                        <span className="sm-confirm-text">{t("rmSnapPolicyConfirmDelete")}</span>
                        <button className="rm-btn-danger-sm" onClick={() => void handleDeletePolicy(p.uuid)}>
                          {t("rmExecute")}
                        </button>
                        <button className="rm-btn-sm" onClick={() => setConfirmDeleteUuid(null)}>
                          {t("cancel")}
                        </button>
                      </span>
                    ) : (
                      <button className="rm-btn-danger-sm" onClick={() => setConfirmDeleteUuid(p.uuid)}>
                        {t("delete")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {policies.length === 0 && <tr><td colSpan={5} className="empty-state">{t("rmSnapNoPolicies")}</td></tr>}
            </tbody>
          </table>
        </>
      )}

      {activeTab === "tamperproof" && (
        <>
          <p style={{ marginBottom: "1rem" }}>{t("rmSnapTamperproofDesc")}</p>

          <div className="create-form">
            <VolumeSelector
              label={t("rmSnapSelectVolume")}
              showUuid
              onSelect={(vol) => { setVolumeUuid(vol?.uuid ?? null); }}
              excludeFlexCache
            />
            <button onClick={loadLockingStatus} className="btn-primary" disabled={!volumeUuid} style={{ marginTop: "0.75rem" }}>{t("rmSnapCheckStatus")}</button>
          </div>

          {lockConfig && (
            <div className="detail-grid" style={{ marginTop: "1rem" }}>
              <div className="detail-card">
                <div className="detail-label">{t("rmVolumeName")}</div>
                <div className="detail-value">{lockConfig.volumeName}</div>
              </div>
              <div className="detail-card">
                <div className="detail-label">{t("rmSnapLockingState")}</div>
                <div className={`detail-value ${lockConfig.snapshotLockingEnabled ? "text-success" : ""}`}>
                  {lockConfig.snapshotLockingEnabled ? `🔒 ${t("stateEnabled")}` : `— ${t("stateDisabled")}`}
                </div>
              </div>
              <div className="detail-card">
                <div className="detail-label">{t("rmSnapLockedCount")}</div>
                <div className="detail-value">{lockConfig.lockedSnapshotCount} / {lockConfig.totalSnapshotCount}</div>
              </div>
              <div className="detail-card">
                <div className="detail-label">{t("rmSnapPolicy")}</div>
                <div className="detail-value">{lockConfig.snapshotPolicy || "—"}</div>
              </div>

              {!lockConfig.snapshotLockingEnabled && (
                <button onClick={handleEnableLockingClick} className="btn-primary" style={{ marginTop: "1rem" }}>
                  🔒 {t("rmSnapEnableLocking")}
                </button>
              )}
            </div>
          )}

          <details style={{ marginTop: "1.5rem" }}>
            <summary>{t("rmSnapTamperproofHow")}</summary>
            <ul>
              <li>{t("rmSnapTamperproofStep1")}</li>
              <li>{t("rmSnapTamperproofStep2")}</li>
              <li>{t("rmSnapTamperproofStep3")}</li>
              <li>{t("rmSnapTamperproofStep4")}</li>
            </ul>
          </details>
        </>
      )}
    </div>
  );
}
