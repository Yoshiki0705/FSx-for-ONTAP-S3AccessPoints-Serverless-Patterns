import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

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
  const { t } = useTranslation();

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
        <h2>🔒 {t("lockTitle")}</h2>
        <p className="loading">{t("loading")}</p>
      </div>
    );
  }

  // Fallback: ONTAP not connected
  if (error) {
    return (
      <div className="protection-section">
        <h2>🔒 {t("lockTitle")}</h2>
        <div className="protection-info">
          <h3>📡 {t("lockOntapRequired")}</h3>
          <p>{t("lockOntapRequiredDesc")}</p>
          <ul>
            <li>{t("envVarsRequired")}: <code>ONTAP_MGMT_IP</code>,
                <code>ONTAP_SECRET_NAME</code>, <code>VOLUME_NAME</code>, <code>SVM_NAME</code></li>
            <li>{t("vpcLambdaReq")}</li>
          </ul>
          <p className="integration-note">
            <strong>{t("demoModeNote")}</strong>: {t("arpDemoModeNote")}
          </p>
          <details>
            <summary>{t("errorDetails")}</summary>
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
        <h2>🔒 {t("lockTitle")}</h2>
        {volumeName && (
          <span className="volume-badge" title="Source volume">
            {t("volume")}: {volumeName}
          </span>
        )}
        <button onClick={loadStatus} className="refresh-btn" title={t("refresh")}>
          ↻
        </button>
      </div>

      {/* Panel selector tabs */}
      <div className="lock-panel-tabs" role="tablist" aria-label="Lock type selection">
        <button
          role="tab"
          aria-selected={activePanel === "snaplock"}
          className={`panel-tab ${activePanel === "snaplock" ? "active" : ""}`}
          onClick={() => setActivePanel("snaplock")}
        >
          🔒 {t("lockTabSnaplock")}
        </button>
        <button
          role="tab"
          aria-selected={activePanel === "s3lock"}
          className={`panel-tab ${activePanel === "s3lock" ? "active" : ""}`}
          onClick={() => setActivePanel("s3lock")}
        >
          🪣 {t("lockTabS3ObjectLock")}
        </button>
        <button
          role="tab"
          aria-selected={activePanel === "tamperproof"}
          className={`panel-tab ${activePanel === "tamperproof" ? "active" : ""}`}
          onClick={() => setActivePanel("tamperproof")}
        >
          🔐 {t("lockTabTamperproof")}
        </button>
      </div>

      {/* Panel A: ONTAP SnapLock */}
      {activePanel === "snaplock" && snaplock && (
        <div className="lock-panel" role="tabpanel" aria-label="ONTAP SnapLock">
          <div className="panel-description">
            <p>{t("lockSnaplockDesc")}</p>
          </div>

          {/* Status badge — System Manager style */}
          <div className="status-indicator-large">
            <div className={`status-dot status-dot-${snaplock.type === "non_snaplock" ? "disabled" : "active"}`} />
            <div className="status-label">
              <span className="status-title">
                {snaplock.type === "compliance" && t("lockSnaplockCompliance")}
                {snaplock.type === "enterprise" && t("lockSnaplockEnterprise")}
                {snaplock.type === "non_snaplock" && t("lockSnaplockNotConfigured")}
              </span>
              <span className="status-subtitle">
                {snaplock.type === "compliance" && t("lockSnaplockComplianceDesc")}
                {snaplock.type === "enterprise" && t("lockSnaplockEnterpriseDesc")}
                {snaplock.type === "non_snaplock" && t("lockSnaplockNotConfiguredDesc")}
              </span>
            </div>
          </div>

          {snaplock.type !== "non_snaplock" && (
            <div className="protection-cards">
              <div className="protection-card">
                <div className="card-icon">📅</div>
                <div className="card-content">
                  <h3>{t("lockRetentionPolicy")}</h3>
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
                    <h3>{t("lockAutocommit")}</h3>
                    <p>{snaplock.autocommitPeriod}</p>
                    <small>{t("lockAutocommitDesc")}</small>
                  </div>
                </div>
              )}

              {snaplock.complianceClockTime && (
                <div className="protection-card">
                  <div className="card-icon">🕐</div>
                  <div className="card-content">
                    <h3>{t("lockComplianceClock")}</h3>
                    <p>{new Date(snaplock.complianceClockTime).toLocaleString()}</p>
                    <small>{t("lockComplianceClockDesc")}</small>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="panel-footer-note">
            {t("lockScope")}
          </div>
        </div>
      )}

      {/* Panel B: S3 Object Lock */}
      {activePanel === "s3lock" && (
        <div className="lock-panel" role="tabpanel" aria-label="S3 Object Lock">
          <div className="panel-description">
            <p>{t("lockS3ObjectLockDesc")}</p>
          </div>

          <div className="status-indicator-large">
            <div className="status-dot status-dot-info" />
            <div className="status-label">
              <span className="status-title">{t("lockS3OutputTitle")}</span>
              <span className="status-subtitle">{t("lockS3OutputDesc")}</span>
            </div>
          </div>

          <div className="protection-cards">
            <div className="protection-card">
              <div className="card-icon">🪣</div>
              <div className="card-content">
                <h3>{t("lockS3Governance")}</h3>
                <p>{t("lockS3GovernanceRecommended")}</p>
                <small>{t("lockS3GovernanceDesc")}</small>
              </div>
            </div>

            <div className="protection-card">
              <div className="card-icon">🔒</div>
              <div className="card-content">
                <h3>{t("lockS3Compliance")}</h3>
                <p>{t("lockS3ComplianceFor")}</p>
                <small>{t("lockS3ComplianceDesc")}</small>
              </div>
            </div>

            <div className="protection-card">
              <div className="card-icon">⚖️</div>
              <div className="card-content">
                <h3>{t("lockS3LegalHold")}</h3>
                <p>{t("lockS3LegalHoldIndefinite")}</p>
                <small>{t("lockS3LegalHoldDesc")}</small>
              </div>
            </div>
          </div>

          <div className="panel-footer-note">
            {t("lockS3Scope")}
          </div>
        </div>
      )}

      {/* Panel C: Tamperproof Snapshot */}
      {activePanel === "tamperproof" && (
        <div className="lock-panel" role="tabpanel" aria-label="Tamperproof Snapshot">
          <div className="panel-description">
            <p>{t("lockTamperproofDesc")}</p>
          </div>

          <div className="status-indicator-large">
            <div className={`status-dot status-dot-${snapshotLockingEnabled ? "active" : "disabled"}`} />
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

          {snapshotLockingEnabled && (
            <div className="protection-cards">
              <div className="protection-card">
                <div className="card-icon">🔐</div>
                <div className="card-content">
                  <h3>{t("lockTamperproofHowTo")}</h3>
                  <p>{t("lockTamperproofHowToDesc")}</p>
                </div>
              </div>

              <div className="protection-card">
                <div className="card-icon">🛡️</div>
                <div className="card-content">
                  <h3>{t("lockTamperproofProtection")}</h3>
                  <p>{t("lockTamperproofProtectionDesc")}</p>
                </div>
              </div>

              <div className="protection-card">
                <div className="card-icon">🤖</div>
                <div className="card-content">
                  <h3>{t("lockTamperproofArpIntegration")}</h3>
                  <p>{t("lockTamperproofArpIntegrationDesc")}</p>
                </div>
              </div>
            </div>
          )}

          <div className="panel-footer-note">
            {t("lockTamperproofFsxNote")}
          </div>
        </div>
      )}
    </div>
  );
}
