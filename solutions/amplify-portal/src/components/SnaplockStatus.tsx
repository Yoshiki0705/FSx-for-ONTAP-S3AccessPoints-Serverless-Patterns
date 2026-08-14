import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../i18n";
import { errorMessage, failureDiagnosis, unwrap } from "../lib/portalQuery";
import { adminMutate, adminQuery, dispatch, protectionMutate, protectionQuery } from "../lib/dispatch";
import { daysFromNow, type SnapshotId } from "../lib/dispatchActions";
import { useActiveSvm } from "../hooks/useActiveSvm";
import { useStorageAdmin } from "../hooks/useStorageAdmin";
import { OntapFailureNotice } from "./OntapFailureNotice";
import { SnaplockConfirmDialog } from "./SnaplockConfirmDialog";
import { VolumeScopeBadge } from "./VolumeScopeBadge";
import { SvmSelector } from "./admin/SvmSelector";
import { VolumeSelector } from "./admin/VolumeSelector";
import type { SnaplockIntent } from "../utils/snaplockConsequences";

interface SnaplockData {
  type: string;
  complianceClockTime: string;
  expiryTime: string;
  isAuditLog: boolean;
  autocommitPeriod: string;
  retentionPeriod: {
    defaultPeriod: string;
    minimumPeriod: string;
    maximumPeriod: string;
  };
}

interface LockedSnapshot {
  name: string;
  createTime: string;
  expiryTime: string;
  snaplockExpiryTime: string;
  isLocked: boolean;
  /**
   * The snapshot's UUID, branded at the boundary it arrives on.
   *
   * Branding here rather than where it is used is the point: a value branded at the
   * call site could be a name that happened to be in scope, which is the mistake
   * this is meant to catch.
   */
  snapshotId: SnapshotId;
}

interface SnaplockVolume {
  name: string;
  uuid: string;
  snaplockType: string;
  sizeGiB: number;
  state: string;
}

interface UnlockedSnapshot {
  name: string;
  createTime: string;
  snapshotId: SnapshotId;
}

/**
 * Lock — Content Immutability Dashboard
 *
 * P1 Enhancement: Inline resource management in each tab:
 * - SnapLock tab: Lists all SnapLock volumes with type & retention details
 * - Tamperproof tab: Locked snapshots table + inline Lock action with retention selector
 * - S3 Object Lock tab: Informational (not applicable to FSx for ONTAP S3 AP)
 */
export function SnaplockStatus() {
  // The volume the snapshot and SnapLock panels describe. Empty means the configured
  // one, which is the handler's default and what a reader without the storage-admin
  // group sees. It flows into the snapshot listing and into the lock, so a lock cannot
  // be applied to a snapshot of a volume other than the one on screen.
  const [selectedVolume, setSelectedVolume] = useState("");
  // See ArpStatus: a volume name does not survive an SVM change, and a lock applied to
  // a name resolved in the wrong scope cannot be undone.
  const activeSvm = useActiveSvm();
  const [svmAtSelection, setSvmAtSelection] = useState(activeSvm);
  const volumeInScope = svmAtSelection === activeSvm ? selectedVolume : "";
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
  const [success, setSuccess] = useState<string | null>(null);
  /** Set while the consequence dialog is open; null when nothing is pending. */
  const [pendingSnaplock, setPendingSnaplock] = useState<SnaplockIntent | null>(null);
  const [activePanel, setActivePanel] = useState<"snaplock" | "s3lock" | "tamperproof">("snaplock");

  // Lock form state
  const [lockTargetSnap, setLockTargetSnap] = useState("");
  const [lockRetentionDays, setLockRetentionDays] = useState(30);
  const [lockingInProgress, setLockingInProgress] = useState(false);

  // S3 Object Lock configuration form
  const [s3BucketFilter, setS3BucketFilter] = useState("");
  const [s3SelectedBucket, setS3SelectedBucket] = useState("");
  // Narrowed to the two modes ONTAP accepts, so a third value cannot reach the
  // action. It used to be a bare string, and the action's own type is the only
  // thing that would have noticed.
  const [s3LockMode, setS3LockMode] = useState<"GOVERNANCE" | "COMPLIANCE">("GOVERNANCE");
  const [s3LockDays, setS3LockDays] = useState(1);
  const [s3Configuring, setS3Configuring] = useState(false);
  const [showS3Config, setShowS3Config] = useState(false);

  const { t } = useTranslation();
  const isStorageAdmin = useStorageAdmin();

  // Four independent fetches, so four queries. Only the first gates the page;
  // the other three feed panels that degrade to empty, which is also why they
  // swallowed their errors before.
  const statusQuery = useQuery({
    queryKey: ["protection", "getSnaplockStatus", activeSvm || null, volumeInScope || null],
    queryFn: () =>
      unwrap<{
        volumeName?: string;
        snaplock?: SnaplockData;
        snapshotLockingEnabled?: boolean;
      }>(
        dispatch("protectionQuery", {
          action: "getSnaplockStatus",
          params: volumeInScope ? { volumeName: volumeInScope } : {},
        }),
      ),
  });

  // Locked and unlocked come from one listing, so they are split here rather
  // than kept as two pieces of state that could disagree.
  const snapshotsQuery = useQuery({
    queryKey: ["protection", "listSnapshots", 50, activeSvm || null, volumeInScope || null],
    queryFn: async () => {
      const data = await protectionQuery<{ snapshots?: LockedSnapshot[] }>({
        action: "listSnapshots",
        params: volumeInScope
          ? { maxResults: 50, volumeName: volumeInScope }
          : { maxResults: 50 },
      });
      return data?.snapshots ?? [];
    },
  });

  const volumesQuery = useQuery({
    queryKey: ["admin", "snaplockVolumes"],
    queryFn: async () => {
      const data = await adminQuery<{ volumes?: SnaplockVolume[] }>({ action: "listVolumes" });
      return (data?.volumes ?? []).filter(
        (v) => v.snaplockType && v.snaplockType !== "non_snaplock",
      );
    },
  });

  const s3LockQuery = useQuery({
    queryKey: ["admin", "getS3ObjectLockStatus"],
    queryFn: async () => {
      const data = await adminQuery<{
        configured: boolean;
        bucket: string | null;
        objectLockEnabled: boolean;
        defaultRetention: { mode: string; days?: number; years?: number } | null;
        message?: string;
      }>({ action: "getS3ObjectLockStatus" });
      return data ?? null;
    },
  });

  // The bucket picker only opens with the config form, and the filter is part of
  // the key, so typing re-queries without a separate loader call.
  const s3BucketsQuery = useQuery({
    queryKey: ["admin", "listS3Buckets", s3BucketFilter],
    enabled: showS3Config,
    queryFn: async () => {
      const data = await adminQuery<{ buckets?: { name: string }[] }>({
        action: "listS3Buckets",
        params: { nameFilter: s3BucketFilter },
      });
      return data?.buckets ?? [];
    },
  });

  const snaplock = statusQuery.data?.snaplock ?? null;
  const snapshotLockingEnabled = statusQuery.data?.snapshotLockingEnabled ?? false;
  const volumeName = statusQuery.data?.volumeName ?? "";
  const allSnapshots = snapshotsQuery.data ?? [];
  const lockedSnapshots = allSnapshots.filter((s) => s.isLocked);
  const unlockedSnapshots: UnlockedSnapshot[] = allSnapshots
    .filter((s) => !s.isLocked)
    .map((s) => ({ name: s.name, createTime: s.createTime, snapshotId: s.snapshotId }));
  // A snapshot without a UUID cannot be addressed by the lock call, so offering
  // it would only produce a rejected request.
  const lockableSnapshots = unlockedSnapshots.filter((s) => !!s.snapshotId);
  const selectedSnapshotName =
    lockableSnapshots.find((s) => s.snapshotId === lockTargetSnap)?.name ?? "";
  const snaplockVolumes = volumesQuery.data ?? [];
  const s3LockStatus = s3LockQuery.data ?? null;
  const s3Buckets = s3BucketsQuery.data ?? [];

  const loading = statusQuery.isPending;
  // Kept apart because only the load error carries a diagnosis class, and only the
  // load error means "there is no ONTAP data to show". A failed lock action used to
  // be able to replace the whole panel with connection advice.
  const loadError = errorMessage(statusQuery.error, "Failed to load status");
  const error = actionError ?? loadError;

  // The lock and configure handlers report through their own state, so a failed
  // action is never mistaken for a failed load.
  const loadLockedSnapshots = () => void snapshotsQuery.refetch();
  const loadS3ObjectLockStatus = () => void s3LockQuery.refetch();

  /** The refresh button reloads the three panels the header covers. */
  const refreshAll = () => {
    void statusQuery.refetch();
    void snapshotsQuery.refetch();
    void volumesQuery.refetch();
  };

  const handleS3BucketSearch = (value: string) => setS3BucketFilter(value);

  /**
   * COMPLIANCE retention cannot be shortened or removed, and GOVERNANCE can only
   * be overridden by a caller holding the bypass permission. Either way the
   * operator should see which of the two they picked before it applies.
   */
  const handleConfigureS3LockClick = () => {
    if (!s3SelectedBucket) { setError(t("lockS3SelectBucketRequired")); return; }
    setError(null);
    setPendingSnaplock({
      kind: "s3ObjectLock",
      bucket: s3SelectedBucket,
      mode: s3LockMode === "COMPLIANCE" ? "COMPLIANCE" : "GOVERNANCE",
      days: s3LockDays,
    });
  };

  /** A snapshot lock can be extended but never shortened or released. */
  const handleLockSnapshotClick = () => {
    if (!lockTargetSnap) { setError(t("lockSelectSnapshotRequired")); return; }
    if (lockRetentionDays <= 0) { setError(t("lockRetentionRequired")); return; }
    setError(null);
    setPendingSnaplock({
      kind: "lockSnapshot",
      // The selection carries the snapshot UUID because that is what the lock
      // call needs; the dialog names the snapshot, so the label is resolved back
      // for display and falls back to the UUID if the list has since reloaded.
      snapshotName: selectedSnapshotName || lockTargetSnap,
      retentionDays: lockRetentionDays,
    });
  };

  const handleConfigureS3Lock = async () => {
    if (!s3SelectedBucket) { setError(t("lockS3SelectBucketRequired")); return; }
    setS3Configuring(true);
    setError(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "putS3ObjectLockRetention",
        params: {
          bucket: s3SelectedBucket,
          mode: s3LockMode,
          days: s3LockDays,
          acknowledgeIrreversible: true,
        },
      });
      if (data) {
        if (data.success) {
          setSuccess(t("lockS3Configured"));
          setTimeout(() => setSuccess(null), 3000);
          loadS3ObjectLockStatus();
          setShowS3Config(false);
        } else setError(data.error || "Configuration failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Configuration failed");
    } finally {
      setS3Configuring(false);
    }
  };

  const handleLockSnapshot = async () => {
    if (!lockTargetSnap) { setError(t("lockSelectSnapshotRequired")); return; }
    if (lockRetentionDays <= 0) { setError(t("lockRetentionRequired")); return; }
    setLockingInProgress(true);
    setError(null);
    try {
      // The action takes the snapshot UUID and an absolute expiry, not a name and
      // a duration. Sending the latter made this button fail every time with
      // "snapshotId and expiryTime required" — the version history panel had the
      // contract right, this one did not.
      //
      // The UUID is taken from the listing rather than from the select's value: a
      // DOM value is a string, and branding one at this point would accept whatever
      // string was there. Resolving it also catches a selection left stale by a
      // reload, which would previously have been sent as-is.
      const selected = lockableSnapshots.find((s) => s.snapshotId === lockTargetSnap);
      if (!selected) { setError(t("lockSelectSnapshotRequired")); return; }

      const data = await protectionMutate<{ success?: boolean }>({
        action: "lockSnapshot",
        params: {
          snapshotId: selected.snapshotId,
          expiryTime: daysFromNow(lockRetentionDays),
          acknowledgeIrreversible: true,
          // The volume the listing came from. Without it the handler resolves the
          // configured volume and looks for this snapshot there -- on any other volume
          // that is a lock applied to the wrong subject, and a lock cannot be undone.
          ...(volumeInScope ? { volumeName: volumeInScope } : {}),
        },
      });
      if (data) {
        if (data.success) {
          setSuccess(t("lockSnapshotLocked"));
          setLockTargetSnap("");
          setTimeout(() => setSuccess(null), 3000);
          loadLockedSnapshots();
        } else setError(data.error || "Lock failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lock failed");
    } finally {
      setLockingInProgress(false);
    }
  };

  const formatDate = (iso: string | null | undefined) => {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleString(); } catch { return iso; }
  };

  // Only while there is nothing to show. `isPending` is true again for every new query
  // key, so returning the loading screen on it replaced the whole page -- including the
  // volume selector -- and the selector came back with its state reset. The selection
  // survived in the parent, so the badge was right while the dropdown read "select a
  // volume": one control disagreeing with another about the same fact.
  if (loading && !statusQuery.data) {
    return (
      <div className="protection-section">
        <h2>🔒 {t("lockTitle")}</h2>
        <p className="loading">{t("loading")}</p>
      </div>
    );
  }

  // ONTAP connection error: still show tabs (S3 Object Lock doesn't need ONTAP)
  const ontapError = loadError && !snaplock && !snaplockVolumes.length ? loadError : null;
  const ontapDiagnosis = failureDiagnosis(statusQuery.error);

  return (
    <div className="protection-section">
      {pendingSnaplock && (
        <SnaplockConfirmDialog
          intent={pendingSnaplock}
          onCancel={() => setPendingSnaplock(null)}
          onConfirm={() => {
            const intent = pendingSnaplock;
            setPendingSnaplock(null);
            if (intent.kind === "s3ObjectLock") void handleConfigureS3Lock();
            else void handleLockSnapshot();
          }}
        />
      )}
      <div className="protection-header">
        <h2>🔒 {t("lockTitle")}</h2>
        {/* From the response, so it names the volume these panels describe, and it says
            which of the two it is: the selection, or the deployment's default. */}
        <VolumeScopeBadge volumeName={volumeName} isDefault={!volumeInScope} />

        <button onClick={refreshAll} className="refresh-btn">↻</button>
      </div>

      {/* The scope, on a row of its own: file system (fixed by the connection) then SVM
          then volume. On the title row these overflowed and the refresh button dropped
          below them, and a hierarchy that wraps does not read as one. */}
      {isStorageAdmin === true && (
        <div className="protection-scope">
          {/* No leading "scope" label: the two controls are labelled already, and a
              third label above them read as a duplicate of the SVM one. The chevron
              carries the narrowing instead. */}
          <SvmSelector />
          <span className="protection-scope-chain" aria-hidden="true">›</span>
          <VolumeSelector
            label={t("rmSelectVolume")}
            onSelect={(vol) => {
              setSelectedVolume(vol?.name ?? "");
              setSvmAtSelection(activeSvm);
            }}
          />
        </div>
      )}

      {error && !ontapError && <div className="error-message">{error}</div>}
      {success && <div className="success-message">{success}</div>}

      {/* Tab selector */}
      <div className="lock-panel-tabs" role="tablist">
        <button role="tab" aria-selected={activePanel === "snaplock"}
          className={`panel-tab ${activePanel === "snaplock" ? "active" : ""}`}
          onClick={() => setActivePanel("snaplock")}>
          🔒 ONTAP SnapLock
        </button>
        <button role="tab" aria-selected={activePanel === "s3lock"}
          className={`panel-tab ${activePanel === "s3lock" ? "active" : ""}`}
          onClick={() => setActivePanel("s3lock")}>
          🪣 S3 Object Lock
        </button>
        <button role="tab" aria-selected={activePanel === "tamperproof"}
          className={`panel-tab ${activePanel === "tamperproof" ? "active" : ""}`}
          onClick={() => setActivePanel("tamperproof")}>
          🔐 Tamperproof Snapshot
        </button>
      </div>

      {/* === Tab A: ONTAP SnapLock === */}
      {activePanel === "snaplock" && (
        <div className="lock-panel" role="tabpanel" aria-label={t("slkOntapAria")}>
          {ontapError ? (
            <OntapFailureNotice error={ontapError} {...ontapDiagnosis} />
          ) : (
            <>
              {/* Status summary */}
              {snaplock && snaplock.type !== "non_snaplock" ? (
            <div className="status-indicator-large">
              <div className="status-dot status-dot-active" />
              <div className="status-label">
                <span className="status-title">
                  {snaplock.type === "compliance" ? "🔒 Compliance Mode" : "🔐 Enterprise Mode"}
                </span>
                <span className="status-subtitle">
                  {snaplock.type === "compliance"
                    ? t("lockSnaplockComplianceDesc")
                    : t("lockSnaplockEnterpriseDesc")}
                </span>
              </div>
            </div>
          ) : (
            <div className="status-indicator-large">
              <div className="status-dot status-dot-disabled" />
              <div className="status-label">
                <span className="status-title">{t("lockSnaplockNotConfigured")}</span>
                <span className="status-subtitle">{t("lockSnaplockNotConfiguredDesc")}</span>
              </div>
            </div>
          )}

          {/* P1: Inline SnapLock volumes list */}
          <h4 style={{ marginTop: "1.5rem" }}>🔒 {t("lockSnaplockVolumes")} ({snaplockVolumes.length})</h4>

          {snaplockVolumes.length > 0 ? (
            <table className="admin-table" style={{ marginTop: "0.5rem" }}>
              <thead>
                <tr>
                  <th>{t("lockVolName")}</th>
                  <th>{t("rmSnaplockType")}</th>
                  <th>{t("rmVolumeSize")}</th>
                  <th>{t("rmState")}</th>
                </tr>
              </thead>
              <tbody>
                {snaplockVolumes.map((vol) => (
                  <tr key={vol.uuid}>
                    <td>{vol.name}</td>
                    <td>
                      <span className={`state-badge ${vol.snaplockType === "compliance" ? "state-warning" : "state-online"}`}>
                        {vol.snaplockType === "compliance" ? "🔒 Compliance" : "🔐 Enterprise"}
                      </span>
                    </td>
                    <td>{vol.sizeGiB} GiB</td>
                    <td>
                      <span className={`state-badge ${vol.state === "online" ? "state-online" : "state-offline"}`}>
                        {vol.state}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="empty-state" style={{ marginTop: "0.5rem" }}>{t("lockNoSnaplockVolumes")}</p>
          )}

          {/* Retention config cards (when SnapLock is configured on primary volume) */}
          {snaplock && snaplock.type !== "non_snaplock" && (
            <div className="detail-grid" style={{ marginTop: "1rem" }}>
              <div className="detail-card">
                <div className="detail-label">{t("rmRetentionDefault")}</div>
                <div className="detail-value">{snaplock.retentionPeriod?.defaultPeriod || "—"}</div>
              </div>
              <div className="detail-card">
                <div className="detail-label">{t("rmRetentionMin")}</div>
                <div className="detail-value">{snaplock.retentionPeriod?.minimumPeriod || "—"}</div>
              </div>
              <div className="detail-card">
                <div className="detail-label">{t("rmRetentionMax")}</div>
                <div className="detail-value">{snaplock.retentionPeriod?.maximumPeriod || "—"}</div>
              </div>
              {snaplock.complianceClockTime && (
                <div className="detail-card">
                  <div className="detail-label">{t("lockComplianceClock")}</div>
                  <div className="detail-value">{formatDate(snaplock.complianceClockTime)}</div>
                </div>
              )}
              {snaplock.autocommitPeriod && snaplock.autocommitPeriod !== "none" && (
                <div className="detail-card">
                  <div className="detail-label">{t("lockAutocommit")}</div>
                  <div className="detail-value">{snaplock.autocommitPeriod}</div>
                </div>
              )}
            </div>
          )}

          <div style={{ marginTop: "1rem" }}>
            <button className="btn-secondary" onClick={() => { sessionStorage.setItem("rm-panel", "volumes"); window.location.hash = "resources"; }}>
              🔧 {t("lockGoToVolumeManager")}
            </button>
          </div>
            </>
          )}
        </div>
      )}

      {/* === Tab B: S3 Object Lock === */}
      {activePanel === "s3lock" && (
        <div className="lock-panel" role="tabpanel" aria-label={t("slkS3Aria")}>
          {/* Status indicator */}
          <div className="status-indicator-large">
            <div className={`status-dot ${s3LockStatus?.objectLockEnabled ? "status-dot-active" : "status-dot-disabled"}`} />
            <div className="status-label">
              <span className="status-title">
                {s3LockStatus?.objectLockEnabled
                  ? `✅ ${t("lockS3Enabled")}`
                  : t("lockS3NotEnabled")}
              </span>
              <span className="status-subtitle">
                {s3LockStatus?.objectLockEnabled
                  ? t("lockS3EnabledDesc")
                  : s3LockStatus?.configured === false
                    ? (s3LockStatus.message || t("lockS3NotConfiguredDesc"))
                    : t("lockS3NotEnabledDesc")}
              </span>
            </div>
          </div>

          {/* Configuration details (when enabled) */}
          {s3LockStatus?.objectLockEnabled && s3LockStatus.defaultRetention && (
            <div className="detail-grid" style={{ marginTop: "1rem" }}>
              <div className="detail-card">
                <div className="detail-label">{t("lockS3Bucket")}</div>
                <div className="detail-value"><code>{s3LockStatus.bucket}</code></div>
              </div>
              <div className="detail-card">
                <div className="detail-label">{t("lockS3Mode")}</div>
                <div className="detail-value">
                  {s3LockStatus.defaultRetention.mode === "GOVERNANCE"
                    ? `🔒 Governance`
                    : `🔐 Compliance`}
                </div>
              </div>
              <div className="detail-card">
                <div className="detail-label">{t("lockS3Retention")}</div>
                <div className="detail-value">
                  {s3LockStatus.defaultRetention.days
                    ? `${s3LockStatus.defaultRetention.days} ${t("rmDays")}`
                    : s3LockStatus.defaultRetention.years
                      ? `${s3LockStatus.defaultRetention.years} years`
                      : "—"}
                </div>
              </div>
            </div>
          )}

          {/* S3 Object Lock configuration form */}
          <div style={{ marginTop: "1.5rem" }}>
            {/* Opening the form enables the bucket query, so no explicit load. */}
            <button className="btn-primary" onClick={() => setShowS3Config(!showS3Config)}>
              🔧 {t("lockS3ConfigureBtn")}
            </button>
          </div>

          {showS3Config && (
            <div className="create-form" style={{ marginTop: "1rem" }}>
              <h4>{t("lockS3ConfigureTitle")}</h4>
              <div className="form-row">
                <div className="form-group">
                  <label>{t("lockS3Bucket")}</label>
                  <input
                    type="text"
                    value={s3BucketFilter}
                    onChange={(e) => handleS3BucketSearch(e.target.value)}
                    placeholder={t("lockS3BucketSearchPlaceholder")}
                    style={{ marginBottom: "0.25rem" }}
                  />
                  <select value={s3SelectedBucket} onChange={(e) => setS3SelectedBucket(e.target.value)}>
                    <option value="">{t("lockS3SelectBucket")}</option>
                    {s3Buckets.map((b) => (
                      <option key={b.name} value={b.name}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                  <small>{t("lockS3BucketNote")}</small>
                </div>
                <div className="form-group">
                  <label>{t("lockS3Mode")}</label>
                  {/* A select yields a string, so the two options are narrowed back
                      here rather than widening the state to accept a third mode. */}
                  <select
                    value={s3LockMode}
                    onChange={(e) =>
                      setS3LockMode(e.target.value === "COMPLIANCE" ? "COMPLIANCE" : "GOVERNANCE")
                    }
                  >
                    <option value="GOVERNANCE">Governance — {t("lockS3GovernanceHint")}</option>
                    <option value="COMPLIANCE">Compliance — {t("lockS3ComplianceHint")}</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>{t("lockS3Retention")}</label>
                  <select value={s3LockDays} onChange={(e) => setS3LockDays(Number(e.target.value))}>
                    <option value={1}>1 {t("rmDays")}</option>
                    <option value={7}>7 {t("rmDays")}</option>
                    <option value={30}>30 {t("rmDays")}</option>
                    <option value={90}>90 {t("rmDays")}</option>
                    <option value={365}>1 year</option>
                  </select>
                </div>
              </div>
              <button onClick={handleConfigureS3LockClick} className="btn-primary" disabled={s3Configuring || !s3SelectedBucket}>
                {s3Configuring ? t("loading") : t("lockS3ApplyBtn")}
              </button>
              <button onClick={() => setShowS3Config(false)} className="btn-secondary" style={{ marginLeft: "0.5rem" }}>
                {t("cancel")}
              </button>
            </div>
          )}

          <div style={{ marginTop: "1rem", fontSize: "0.85rem", color: "var(--color-text-secondary)" }}>
            {t("lockS3NotApplicableDesc")}
          </div>
        </div>
      )}

      {/* === Tab C: Tamperproof Snapshot === */}
      {activePanel === "tamperproof" && (
        <div className="lock-panel" role="tabpanel" aria-label={t("slkTamperAria")}>
          {ontapError ? (
            <OntapFailureNotice error={ontapError} {...ontapDiagnosis} />
          ) : (
            <>
          {/* Status */}
          <div className="status-indicator-large">
            <div className={`status-dot ${snapshotLockingEnabled ? "status-dot-active" : "status-dot-disabled"}`} />
            <div className="status-label">
              <span className="status-title">
                {snapshotLockingEnabled ? t("lockTamperproofEnabled") : t("lockTamperproofNotEnabled")}
              </span>
              <span className="status-subtitle">
                {snapshotLockingEnabled
                  ? t("lockTamperproofEnabledDesc")
                  : t("lockTamperproofEnableCmd")}
              </span>
            </div>
          </div>

          {snapshotLockingEnabled ? (
            <>
              {/* P1: Inline Lock Snapshot action */}
              <div className="create-form" style={{ marginTop: "1rem" }}>
                <h4>🔐 {t("lockSnapshotAction")}</h4>
                <div className="form-row">
                  <div className="form-group">
                    <label>{t("lockSelectSnapshot")}</label>
                    <select value={lockTargetSnap} onChange={(e) => setLockTargetSnap(e.target.value)}>
                      <option value="">{t("lockSelectSnapshotPlaceholder")}</option>
                      {/* The value is the UUID because that is what the lock call
                          identifies a snapshot by. Names are not unique enough to
                          address one, and the option text still shows the name. */}
                      {lockableSnapshots.map((s) => (
                        <option key={s.snapshotId} value={s.snapshotId}>
                          {s.name} ({formatDate(s.createTime)})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>{t("lockRetentionPeriod")}</label>
                    <select value={lockRetentionDays} onChange={(e) => setLockRetentionDays(Number(e.target.value))}>
                      <option value={1}>1 {t("rmDays")}</option>
                      <option value={7}>7 {t("rmDays")}</option>
                      <option value={30}>30 {t("rmDays")}</option>
                      <option value={90}>90 {t("rmDays")}</option>
                      <option value={365}>365 {t("rmDays")} (1 year)</option>
                      <option value={1825} title={t("lockSoxTooltip")}>1,825 {t("rmDays")} — SOX/J-SOX (5 {t("lockYears")})</option>
                      <option value={2192} title={t("lockHipaaTooltip")}>2,192 {t("rmDays")} — HIPAA (6 {t("lockYears")})</option>
                      <option value={2557} title={t("lockFiscTooltip")}>2,557 {t("rmDays")} — FISC (7 {t("lockYears")})</option>
                    </select>
                  </div>
                  <div className="form-group" style={{ alignSelf: "flex-end" }}>
                    <button
                      onClick={handleLockSnapshotClick}
                      className="btn-primary"
                      disabled={lockingInProgress || !lockTargetSnap}
                    >
                      {lockingInProgress ? t("loading") : `🔐 ${t("lockLockBtn")}`}
                    </button>
                  </div>
                </div>
                <small style={{ color: "var(--color-text-secondary)" }}>{t("lockRetentionWarning")}</small>
              </div>

              {/* Locked snapshots table */}
              <h4 style={{ marginTop: "1.5rem" }}>🔐 {t("lockLockedSnapshots")} ({lockedSnapshots.length})</h4>

              {lockedSnapshots.length > 0 ? (
                <table className="admin-table" style={{ marginTop: "0.5rem" }}>
                  <thead>
                    <tr>
                      <th>{t("lockSnapName")}</th>
                      <th>{t("lockSnapCreated")}</th>
                      <th>{t("lockSnapLockedUntil")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lockedSnapshots.map((snap) => (
                      <tr key={snap.snapshotId || snap.name}>
                        <td>{snap.name}</td>
                        <td>{formatDate(snap.createTime)}</td>
                        <td>
                          <span className="lock-badge locked">
                            🔐 {formatDate(snap.expiryTime || snap.snaplockExpiryTime)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="empty-state" style={{ marginTop: "0.5rem" }}>{t("lockNoLockedSnapshots")}</p>
              )}
            </>
          ) : (
            <>
              <div className="info-message" style={{ marginTop: "1rem" }}>
                <strong>{t("lockTamperproofHowTo")}</strong>
                <p style={{ margin: "0.5rem 0 0", fontSize: "0.85rem" }}>
                  {t("lockTamperproofHowToDesc")}
                </p>
              </div>

              <button className="btn-primary" style={{ marginTop: "1rem" }}
                onClick={() => { sessionStorage.setItem("rm-panel", "snapshotAdmin"); window.location.hash = "resources"; }}>
                🔧 {t("lockGoToSnapshotAdmin")}
              </button>
            </>
          )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
