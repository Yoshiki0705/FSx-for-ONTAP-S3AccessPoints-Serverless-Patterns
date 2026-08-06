import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";
import { parseResponse } from "../utils/parseResponse";

const client = generateClient<Schema>();

// Parse the JSON string response from generic dispatch endpoints

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
  snapshotId: string;
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
  snapshotId: string;
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
  const [snaplock, setSnaplock] = useState<SnaplockData | null>(null);
  const [snapshotLockingEnabled, setSnapshotLockingEnabled] = useState(false);
  const [volumeName, setVolumeName] = useState("");
  const [lockedSnapshots, setLockedSnapshots] = useState<LockedSnapshot[]>([]);
  const [snaplockVolumes, setSnaplockVolumes] = useState<SnaplockVolume[]>([]);
  const [unlockedSnapshots, setUnlockedSnapshots] = useState<UnlockedSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<"snaplock" | "s3lock" | "tamperproof">("snaplock");

  // Lock form state
  const [lockTargetSnap, setLockTargetSnap] = useState("");
  const [lockRetentionDays, setLockRetentionDays] = useState(30);
  const [lockingInProgress, setLockingInProgress] = useState(false);

  // S3 Object Lock state
  const [s3LockStatus, setS3LockStatus] = useState<{
    configured: boolean;
    bucket: string | null;
    objectLockEnabled: boolean;
    defaultRetention: { mode: string; days?: number; years?: number } | null;
    message?: string;
  } | null>(null);

  // S3 Object Lock configuration form
  const [s3Buckets, setS3Buckets] = useState<{ name: string }[]>([]);
  const [s3BucketFilter, setS3BucketFilter] = useState("");
  const [s3SelectedBucket, setS3SelectedBucket] = useState("");
  const [s3LockMode, setS3LockMode] = useState("GOVERNANCE");
  const [s3LockDays, setS3LockDays] = useState(1);
  const [s3Configuring, setS3Configuring] = useState(false);
  const [showS3Config, setShowS3Config] = useState(false);

  const { t } = useTranslation();

  const loadStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await client.queries.protectionQuery({
        action: "getSnaplockStatus",
        params: JSON.stringify({}),
      });
      const data = parseResponse<{
        volumeName?: string;
        snaplock?: SnaplockData;
        snapshotLockingEnabled?: boolean;
        error?: string;
      }>(response);
      if (data) {
        if (data.error) setError(data.error);
        else {
          setSnaplock(data.snaplock || null);
          setSnapshotLockingEnabled(data.snapshotLockingEnabled || false);
          setVolumeName(data.volumeName || "");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load status");
    } finally {
      setLoading(false);
    }
  };

  const loadLockedSnapshots = async () => {
    try {
      const response = await client.queries.protectionQuery({
        action: "listSnapshots",
        params: JSON.stringify({ maxResults: 50 }),
      });
      const data = parseResponse<{ snapshots?: LockedSnapshot[] }>(response);
      if (data && data.snapshots) {
        setLockedSnapshots(data.snapshots.filter((s) => s.isLocked));
        setUnlockedSnapshots(
          data.snapshots
            .filter((s) => !s.isLocked)
            .map((s) => ({ name: s.name, createTime: s.createTime, snapshotId: s.snapshotId }))
        );
      }
    } catch { /* silent */ }
  };

  const loadSnaplockVolumes = async () => {
    try {
      const response = await client.queries.adminQuery({
        action: "listVolumes",
        params: JSON.stringify({}),
      });
      const data = parseResponse<{ volumes?: SnaplockVolume[] }>(response);
      if (data && data.volumes) {
        setSnaplockVolumes(
          data.volumes.filter((v) => v.snaplockType && v.snaplockType !== "non_snaplock")
        );
      }
    } catch { /* silent — admin query may fail for non-admin users */ }
  };

  const loadS3ObjectLockStatus = async () => {
    try {
      const response = await client.queries.adminQuery({
        action: "getS3ObjectLockStatus",
        params: JSON.stringify({}),
      });
      const data = parseResponse<{
        configured: boolean;
        bucket: string | null;
        objectLockEnabled: boolean;
        defaultRetention: { mode: string; days?: number; years?: number } | null;
        message?: string;
        error?: string;
      }>(response);
      if (data) setS3LockStatus(data);
    } catch { /* silent */ }
  };

  const loadS3Buckets = async (nameFilter?: string) => {
    try {
      const response = await client.queries.adminQuery({
        action: "listS3Buckets",
        params: JSON.stringify({ nameFilter: nameFilter || "" }),
      });
      const data = parseResponse<{ buckets?: { name: string }[] }>(response);
      if (data && data.buckets) setS3Buckets(data.buckets);
    } catch { /* silent */ }
  };

  const handleS3BucketSearch = (value: string) => {
    setS3BucketFilter(value);
    // Debounce not needed here since filtering is client-side in Lambda
    loadS3Buckets(value);
  };

  const handleConfigureS3Lock = async () => {
    if (!s3SelectedBucket) { setError(t("lockS3SelectBucketRequired")); return; }
    setS3Configuring(true);
    setError(null);
    try {
      const response = await client.mutations.adminMutation({
        action: "putS3ObjectLockRetention",
        params: JSON.stringify({
          bucket: s3SelectedBucket,
          mode: s3LockMode,
          days: s3LockDays,
        }),
      });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
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
      const response = await client.mutations.protectionMutation({
        action: "lockSnapshot",
        params: JSON.stringify({
          snapshotName: lockTargetSnap,
          retentionDays: lockRetentionDays,
        }),
      });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
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

  useEffect(() => {
    loadStatus();
    loadLockedSnapshots();
    loadSnaplockVolumes();
    loadS3ObjectLockStatus();
  }, []);

  const formatDate = (iso: string | null | undefined) => {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleString(); } catch { return iso; }
  };

  if (loading) {
    return (
      <div className="protection-section">
        <h2>🔒 {t("lockTitle")}</h2>
        <p className="loading">{t("loading")}</p>
      </div>
    );
  }

  // ONTAP connection error: still show tabs (S3 Object Lock doesn't need ONTAP)
  const ontapError = error && !snaplock && !snaplockVolumes.length;

  return (
    <div className="protection-section">
      <div className="protection-header">
        <h2>🔒 {t("lockTitle")}</h2>
        {volumeName && <span className="volume-badge">{t("volume")}: {volumeName}</span>}
        <button onClick={() => { loadStatus(); loadLockedSnapshots(); loadSnaplockVolumes(); }} className="refresh-btn">↻</button>
      </div>

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
            <div className="protection-info">
              <h3>📡 {t("lockOntapRequired")}</h3>
              <p>{t("lockOntapRequiredDesc")}</p>
              <details>
                <summary>{t("errorDetails")}</summary>
                <pre style={{ fontSize: "0.8rem", padding: "0.5rem", background: "#f5f5f5", borderRadius: "4px" }}>{error}</pre>
              </details>
            </div>
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
            <button className="btn-primary" onClick={() => { setShowS3Config(!showS3Config); if (!showS3Config) loadS3Buckets(); }}>
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
                  <select value={s3LockMode} onChange={(e) => setS3LockMode(e.target.value)}>
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
              <button onClick={handleConfigureS3Lock} className="btn-primary" disabled={s3Configuring || !s3SelectedBucket}>
                {s3Configuring ? t("loading") : t("lockS3ApplyBtn")}
              </button>
              <button onClick={() => setShowS3Config(false)} className="btn-secondary" style={{ marginLeft: "0.5rem" }}>
                {t("cancel")}
              </button>
            </div>
          )}

          <div style={{ marginTop: "1rem", fontSize: "0.85rem", color: "#666" }}>
            {t("lockS3NotApplicableDesc")}
          </div>
        </div>
      )}

      {/* === Tab C: Tamperproof Snapshot === */}
      {activePanel === "tamperproof" && (
        <div className="lock-panel" role="tabpanel" aria-label={t("slkTamperAria")}>
          {ontapError ? (
            <div className="protection-info">
              <h3>📡 {t("lockOntapRequired")}</h3>
              <p>{t("lockOntapRequiredDesc")}</p>
              <details>
                <summary>{t("errorDetails")}</summary>
                <pre style={{ fontSize: "0.8rem", padding: "0.5rem", background: "#f5f5f5", borderRadius: "4px" }}>{error}</pre>
              </details>
            </div>
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
                      {unlockedSnapshots.map((s) => (
                        <option key={s.snapshotId || s.name} value={s.name}>
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
                      onClick={handleLockSnapshot}
                      className="btn-primary"
                      disabled={lockingInProgress || !lockTargetSnap}
                    >
                      {lockingInProgress ? t("loading") : `🔐 ${t("lockLockBtn")}`}
                    </button>
                  </div>
                </div>
                <small style={{ color: "#666" }}>{t("lockRetentionWarning")}</small>
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
