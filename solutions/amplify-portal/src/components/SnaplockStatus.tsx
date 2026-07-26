import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

// Parse the JSON string response from generic dispatch endpoints
function parseResponse<T>(response: { data?: string | null }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === "string" ? JSON.parse(response.data) : response.data;
  } catch { return null; }
}

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

  const { t } = useTranslation();

  const loadStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await (client.queries as any).protectionQuery({
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
      const response = await (client.queries as any).protectionQuery({
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
      const response = await (client.queries as any).adminQuery({
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

  const handleLockSnapshot = async () => {
    if (!lockTargetSnap) { setError(t("lockSelectSnapshotRequired")); return; }
    if (lockRetentionDays <= 0) { setError(t("lockRetentionRequired")); return; }
    setLockingInProgress(true);
    setError(null);
    try {
      const response = await (client.mutations as any).protectionMutation({
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
        <div className="lock-panel" role="tabpanel" aria-label="ONTAP SnapLock">
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
        <div className="lock-panel" role="tabpanel" aria-label="S3 Object Lock">
          <div className="status-indicator-large">
            <div className="status-dot status-dot-info" />
            <div className="status-label">
              <span className="status-title">{t("lockS3NotApplicable")}</span>
              <span className="status-subtitle">{t("lockS3NotApplicableDesc")}</span>
            </div>
          </div>

          <div className="info-message" style={{ marginTop: "1rem" }}>
            <strong>{t("lockS3Alternative")}</strong>
            <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.2rem", fontSize: "0.85rem" }}>
              <li>{t("lockS3AltSnaplock")}</li>
              <li>{t("lockS3AltTamperproof")}</li>
            </ul>
          </div>

          <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}>
            <button className="btn-secondary" onClick={() => setActivePanel("snaplock")}>
              🔒 SnapLock {t("lockTabSwitch")}
            </button>
            <button className="btn-secondary" onClick={() => setActivePanel("tamperproof")}>
              🔐 Tamperproof {t("lockTabSwitch")}
            </button>
          </div>
        </div>
      )}

      {/* === Tab C: Tamperproof Snapshot === */}
      {activePanel === "tamperproof" && (
        <div className="lock-panel" role="tabpanel" aria-label="Tamperproof Snapshot">
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
                      <option value={365}>1 year</option>
                      <option value={730}>2 years</option>
                      <option value={1825}>5 years</option>
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
