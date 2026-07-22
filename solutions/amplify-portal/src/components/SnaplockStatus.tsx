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
 * SnapLock Status component — displays real ONTAP SnapLock volume configuration.
 *
 * Architecture:
 *   AppSync getSnaplockStatus → VPC Lambda → ONTAP REST API
 *   GET /api/storage/volumes?fields=snaplock,snapshot_locking_enabled
 *
 * SnapLock types:
 *   - non_snaplock: Standard volume (no WORM protection)
 *   - compliance: Files cannot be deleted by anyone until retention expires
 *   - enterprise: Files protected but privileged delete available for admin
 *
 * Also displays Tamperproof Snapshot (snapshot_locking_enabled) status,
 * which is a separate feature from SnapLock volumes but related to data immutability.
 */
export function SnaplockStatus() {
  const [snaplock, setSnaplock] = useState<SnaplockData | null>(null);
  const [snapshotLockingEnabled, setSnapshotLockingEnabled] = useState(false);
  const [volumeName, setVolumeName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  const getTypeIcon = (type: string): string => {
    switch (type) {
      case "compliance": return "🔒";
      case "enterprise": return "🛡️";
      case "non_snaplock": return "📂";
      default: return "❓";
    }
  };

  const getTypeLabel = (type: string): string => {
    switch (type) {
      case "compliance": return "Compliance — files cannot be deleted until retention expires (no override)";
      case "enterprise": return "Enterprise — WORM with privileged delete available";
      case "non_snaplock": return "Standard volume — no SnapLock WORM protection";
      default: return type;
    }
  };

  if (loading) {
    return (
      <div className="protection-section">
        <h2>🔒 Lock — Content Immutability</h2>
        <p className="loading">Loading SnapLock status...</p>
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
            <li>The <strong>ListSnapshots Lambda</strong> must be deployed in a VPC subnet
                that can reach the management LIF</li>
            <li>Environment variables required: <code>ONTAP_MGMT_IP</code>,
                <code>ONTAP_SECRET_NAME</code>, <code>VOLUME_NAME</code>, <code>SVM_NAME</code></li>
            <li>Security group must allow outbound TCP/443 to the management LIF IP</li>
          </ul>
          <p className="integration-note">
            <strong>DemoMode note</strong>: File browsing, AI processing, and upload work without
            ONTAP connectivity. Only Data Protection features (SnapLock, Tamperproof Snapshot, ARP)
            require the VPC Lambda → ONTAP REST API path.
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

      <p className="section-description">
        Unified view of content protection locks across ONTAP SnapLock and Tamperproof Snapshot.
        Locked content cannot be modified or deleted until the retention period expires,
        regardless of access privileges.
      </p>

      {snaplock && (
        <div className="lock-subsections">
          {/* SnapLock Volume Status */}
          <div className="lock-subsection">
            <h3>ONTAP SnapLock (Volume-level WORM)</h3>
            <p className="subsection-desc">
              {snaplock.type === "non_snaplock"
                ? "This volume does not have SnapLock enabled. Files can be modified or deleted normally."
                : "Files committed to this SnapLock volume become immutable at the filesystem level. Applies to NFS/SMB/S3 AP access — all protocols respect the lock."}
            </p>
            <div className="protection-cards">
              <div className="protection-card">
                <div className="card-icon">{getTypeIcon(snaplock.type)}</div>
                <div className="card-content">
                  <h3>SnapLock Type</h3>
                  <p>{getTypeLabel(snaplock.type)}</p>
                </div>
              </div>

              {snaplock.type !== "non_snaplock" && (
                <>
                  <div className="protection-card">
                    <div className="card-icon">📅</div>
                    <div className="card-content">
                      <h3>Retention Policy</h3>
                      <p>
                        Default: {snaplock.retentionPeriod.defaultPeriod || "—"}
                      </p>
                      <small>
                        Min: {snaplock.retentionPeriod.minimumPeriod || "—"} /
                        Max: {snaplock.retentionPeriod.maximumPeriod || "—"}
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
                </>
              )}
            </div>
          </div>

          {/* Tamperproof Snapshot Status */}
          <div className="lock-subsection">
            <h3>Tamperproof Snapshot (Snapshot Locking)</h3>
            <p className="subsection-desc">
              When enabled, Snapshots can be locked with an expiry time. Locked Snapshots cannot
              be deleted — even by cluster administrators — until the retention period expires.
              This protects recovery points against insider threats and ransomware that targets backups.
            </p>
            <div className="protection-cards">
              <div className={`protection-card ${snapshotLockingEnabled ? "status-ok" : "status-disabled"}`}>
                <div className="card-icon">{snapshotLockingEnabled ? "🔐" : "🔓"}</div>
                <div className="card-content">
                  <h3>Snapshot Locking</h3>
                  <p>{snapshotLockingEnabled ? "Enabled" : "Not enabled"}</p>
                  <small>
                    {snapshotLockingEnabled
                      ? "Snapshots can be locked with an expiry time via the Snapshots tab"
                      : "Enable with: volume modify -volume <vol> -snapshot-locking-enabled true"}
                  </small>
                </div>
              </div>

              {snapshotLockingEnabled && (
                <div className="protection-card">
                  <div className="card-icon">📸</div>
                  <div className="card-content">
                    <h3>Lock Snapshots</h3>
                    <p>Available in Snapshots tab</p>
                    <small>
                      Select a Snapshot → Lock with retention period. Once locked, it cannot be
                      deleted until expiry.
                    </small>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* S3 Object Lock (informational — applies to output buckets) */}
          <div className="lock-subsection">
            <h3>S3 Object Lock (Output Bucket WORM)</h3>
            <p className="subsection-desc">
              S3 Object Lock on standard S3 buckets used for AI processing output/archive.
              Provides WORM guarantees for objects stored outside FSx for ONTAP.
            </p>
            <div className="protection-cards">
              <div className="protection-card">
                <div className="card-icon">🪣</div>
                <div className="card-content">
                  <h3>Output Buckets</h3>
                  <p>Governance Mode available</p>
                  <small>
                    AI processing results can be locked for compliance retention.
                    Configure via S3 bucket policy (not managed by ONTAP).
                  </small>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
