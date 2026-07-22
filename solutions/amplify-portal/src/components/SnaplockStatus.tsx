import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";

const client = generateClient<Schema>();

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

/**
 * Lock — Content Immutability component.
 *
 * Separated into two distinct panels:
 *   Panel A: ONTAP SnapLock (volume-level WORM) — queries ONTAP REST API
 *   Panel B: S3 Object Lock (bucket-level WORM) — informational for output buckets
 *
 * Also shows Tamperproof Snapshot (snapshot_locking_enabled) status as a
 * distinct feature — it's related to immutability but operates at the
 * snapshot level, not the file level.
 *
 * UI inspired by NetApp System Manager: status badges, retention cards,
 * compliance mode indicators.
 */
export function SnaplockStatus() {
  const [snaplock, setSnaplock] = useState<SnaplockData | null>(null);
  const [snapshotLockingEnabled, setSnapshotLockingEnabled] = useState(false);
  const [volumeName, setVolumeName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<"snaplock" | "s3lock" | "tamperproof">("snaplock");

  const loadStatus = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await client.queries.getSnaplockStatus({});

      if (response.data) {
        const data = response.data as {
          volumeName?: string;
          snaplock?: SnaplockData;
          snapshotLockingEnabled?: boolean;
          error?: string;
        };
        if (data.error) {
          setError(data.error);
        } else {
          setSnaplock(data.snaplock || null);
          setSnapshotLockingEnabled(data.snapshotLockingEnabled || false);
          setVolumeName(data.volumeName || "");
        }
      } else if (response.errors) {
        setError(response.errors.map((e) => e.message).join(", "));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load SnapLock status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  if (loading) {
    return (
      <div className="protection-section">
        <h2>🔒 Lock — Content Immutability</h2>
        <p className="loading">Loading lock status...</p>
      </div>
    );
  }

  // Fallback: ONTAP not connected
  if (error) {
    return (
      <div className="protection-section">
        <h2>🔒 Lock — Content Immutability</h2>
        <div className="protection-info">
          <h3>📡 ONTAP Connection Required</h3>
          <p>
            SnapLock and Tamperproof Snapshot status is retrieved from the ONTAP
            management LIF via REST API. This section will display real-time
            immutability configuration once the connection is configured.
          </p>
          <ul>
            <li>Environment variables required: <code>ONTAP_MGMT_IP</code>,
                <code>ONTAP_SECRET_NAME</code>, <code>VOLUME_NAME</code>, <code>SVM_NAME</code></li>
            <li>VPC Lambda must reach the management LIF (TCP/443)</li>
          </ul>
          <p className="integration-note">
            <strong>DemoMode note</strong>: File browsing, AI processing, and upload work without
            ONTAP connectivity. Only Data Protection features require the VPC Lambda → ONTAP REST API path.
          </p>
          <details>
            <summary>Error details</summary>
            <pre style={{ fontSize: "0.8rem", overflow: "auto", padding: "0.5rem",
                         background: "#f5f5f5", borderRadius: "4px" }}>{error}</pre>
          </details>
        </div>
      </div>
    );
  }

  return (
    <div className="protection-section">
      <div className="protection-header">
        <h2>🔒 Lock — Content Immutability</h2>
        {volumeName && (
          <span className="volume-badge" title="Source volume">
            Volume: {volumeName}
          </span>
        )}
        <button onClick={loadStatus} className="refresh-btn" title="Refresh lock status">
          ↻
        </button>
      </div>

      {/* Panel selector tabs — inspired by System Manager tabbed panels */}
      <div className="lock-panel-tabs" role="tablist" aria-label="Lock type selection">
        <button
          role="tab"
          aria-selected={activePanel === "snaplock"}
          className={`panel-tab ${activePanel === "snaplock" ? "active" : ""}`}
          onClick={() => setActivePanel("snaplock")}
        >
          🔒 ONTAP SnapLock
        </button>
        <button
          role="tab"
          aria-selected={activePanel === "s3lock"}
          className={`panel-tab ${activePanel === "s3lock" ? "active" : ""}`}
          onClick={() => setActivePanel("s3lock")}
        >
          🪣 S3 Object Lock
        </button>
        <button
          role="tab"
          aria-selected={activePanel === "tamperproof"}
          className={`panel-tab ${activePanel === "tamperproof" ? "active" : ""}`}
          onClick={() => setActivePanel("tamperproof")}
        >
          🔐 Tamperproof Snapshot
        </button>
      </div>

      {/* Panel A: ONTAP SnapLock */}
      {activePanel === "snaplock" && snaplock && (
        <div className="lock-panel" role="tabpanel" aria-label="ONTAP SnapLock">
          <div className="panel-description">
            <p>
              Volume-level WORM (Write Once Read Many) protection. Files committed to a
              SnapLock volume become immutable — they cannot be modified or deleted via any
              protocol (NFS/SMB/S3 AP) until the retention period expires.
            </p>
          </div>

          {/* Status badge — System Manager style */}
          <div className="status-indicator-large">
            <div className={`status-dot status-dot-${snaplock.type === "non_snaplock" ? "disabled" : "active"}`} />
            <div className="status-label">
              <span className="status-title">
                {snaplock.type === "compliance" && "Compliance Mode"}
                {snaplock.type === "enterprise" && "Enterprise Mode"}
                {snaplock.type === "non_snaplock" && "Not Configured"}
              </span>
              <span className="status-subtitle">
                {snaplock.type === "compliance" && "Files cannot be deleted by anyone until retention expires — no override possible"}
                {snaplock.type === "enterprise" && "WORM protection with privileged delete available for authorized administrators"}
                {snaplock.type === "non_snaplock" && "This volume does not have SnapLock enabled. Files can be modified or deleted normally."}
              </span>
            </div>
          </div>

          {snaplock.type !== "non_snaplock" && (
            <div className="protection-cards">
              <div className="protection-card">
                <div className="card-icon">📅</div>
                <div className="card-content">
                  <h3>Retention Policy</h3>
                  <p>Default: {snaplock.retentionPeriod?.defaultPeriod || "—"}</p>
                  <small>
                    Min: {snaplock.retentionPeriod?.minimumPeriod || "—"} /
                    Max: {snaplock.retentionPeriod?.maximumPeriod || "—"}
                  </small>
                </div>
              </div>

              {snaplock.autocommitPeriod && (
                <div className="protection-card">
                  <div className="card-icon">⏱️</div>
                  <div className="card-content">
                    <h3>Autocommit</h3>
                    <p>{snaplock.autocommitPeriod}</p>
                    <small>Files auto-committed to WORM after this period of inactivity</small>
                  </div>
                </div>
              )}

              {snaplock.complianceClockTime && (
                <div className="protection-card">
                  <div className="card-icon">🕐</div>
                  <div className="card-content">
                    <h3>Compliance Clock</h3>
                    <p>{new Date(snaplock.complianceClockTime).toLocaleString()}</p>
                    <small>Tamperproof clock — cannot be reset or adjusted</small>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="panel-footer-note">
            <strong>Scope</strong>: Applies to all files on this volume accessed via NFS, SMB, or S3 AP.
            Regulatory coverage: SEC 17a-4, FISC, HIPAA, NARA records retention.
          </div>
        </div>
      )}

      {/* Panel B: S3 Object Lock */}
      {activePanel === "s3lock" && (
        <div className="lock-panel" role="tabpanel" aria-label="S3 Object Lock">
          <div className="panel-description">
            <p>
              Bucket-level WORM for S3 output buckets. Protects AI processing results,
              compliance reports, and archived exports stored in standard S3 (outside FSx for ONTAP).
            </p>
          </div>

          <div className="status-indicator-large">
            <div className="status-dot status-dot-info" />
            <div className="status-label">
              <span className="status-title">Output Bucket Protection</span>
              <span className="status-subtitle">
                S3 Object Lock is configured on output buckets separately from ONTAP.
                This panel shows the recommended configuration.
              </span>
            </div>
          </div>

          <div className="protection-cards">
            <div className="protection-card">
              <div className="card-icon">🪣</div>
              <div className="card-content">
                <h3>Governance Mode</h3>
                <p>Recommended for AI output</p>
                <small>
                  Objects locked for a retention period. Authorized users can override
                  with <code>s3:BypassGovernanceRetention</code> permission.
                </small>
              </div>
            </div>

            <div className="protection-card">
              <div className="card-icon">🔒</div>
              <div className="card-content">
                <h3>Compliance Mode</h3>
                <p>For regulatory archives</p>
                <small>
                  Objects cannot be deleted or overwritten by anyone — including root —
                  until the retention period expires. Use for SEC 17a-4, HIPAA.
                </small>
              </div>
            </div>

            <div className="protection-card">
              <div className="card-icon">⚖️</div>
              <div className="card-content">
                <h3>Legal Hold</h3>
                <p>Indefinite retention</p>
                <small>
                  Prevents deletion regardless of retention period. Use during litigation
                  or investigation holds.
                </small>
              </div>
            </div>
          </div>

          <div className="panel-footer-note">
            <strong>Scope</strong>: Applies to standard S3 buckets used for AI processing output
            (Athena results, Textract exports, classification reports). Does not apply to
            FSx for ONTAP S3 AP — use ONTAP SnapLock for source data protection.
          </div>
        </div>
      )}

      {/* Panel C: Tamperproof Snapshot */}
      {activePanel === "tamperproof" && (
        <div className="lock-panel" role="tabpanel" aria-label="Tamperproof Snapshot">
          <div className="panel-description">
            <p>
              Snapshot-level locking. When enabled, individual Snapshots can be locked with
              an expiry time — they cannot be deleted even by cluster administrators until
              the retention period expires. Protects recovery points against insider threats
              and ransomware that targets backup deletion.
            </p>
          </div>

          <div className="status-indicator-large">
            <div className={`status-dot status-dot-${snapshotLockingEnabled ? "active" : "disabled"}`} />
            <div className="status-label">
              <span className="status-title">
                {snapshotLockingEnabled ? "Enabled" : "Not Enabled"}
              </span>
              <span className="status-subtitle">
                {snapshotLockingEnabled
                  ? "Snapshots can be locked with expiry time via the Snapshots section (🔒 Lock button)"
                  : "Enable with: volume modify -volume <vol> -snapshot-locking-enabled true"}
              </span>
            </div>
          </div>

          {snapshotLockingEnabled && (
            <div className="protection-cards">
              <div className="protection-card">
                <div className="card-icon">🔐</div>
                <div className="card-content">
                  <h3>How to Lock</h3>
                  <p>Snapshots section → 🔒 Lock button</p>
                  <small>Select retention (1-365 days). Once locked, cannot be shortened.</small>
                </div>
              </div>

              <div className="protection-card">
                <div className="card-icon">🛡️</div>
                <div className="card-content">
                  <h3>Protection Scope</h3>
                  <p>Admin-proof</p>
                  <small>
                    Locked snapshots survive even privileged-delete attempts.
                    Neither fsxadmin nor ONTAP CLI can remove them before expiry.
                  </small>
                </div>
              </div>

              <div className="protection-card">
                <div className="card-icon">🤖</div>
                <div className="card-content">
                  <h3>ARP Integration</h3>
                  <p>Auto-locked on detection</p>
                  <small>
                    ARP-triggered snapshots are automatically locked when ransomware
                    activity is detected (prevents attacker from deleting recovery points).
                  </small>
                </div>
              </div>
            </div>
          )}

          <div className="panel-footer-note">
            <strong>Note</strong>: On FSx for ONTAP, SnapLock is included at no additional cost.
            Tamperproof Snapshot uses the same SnapLock compliance clock infrastructure
            to enforce retention on individual snapshots.
          </div>
        </div>
      )}
    </div>
  );
}
