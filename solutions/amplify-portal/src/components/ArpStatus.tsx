import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

interface ArpData {
  state: string;
  attackProbability: string;
  dryRunStartTime: string;
  surgeAsNormal: boolean;
}

/**
 * ARP/AI Ransomware Protection Status component.
 *
 * UI inspired by NetApp System Manager:
 * - Large status indicator (dot + label) at top
 * - Threat assessment panel with severity color
 * - Protection details cards
 * - Action links to related sections (Snapshots for ARP-triggered recovery)
 *
 * Architecture:
 *   AppSync getArpStatus → VPC Lambda → ONTAP REST API
 *   GET /api/storage/volumes?fields=anti_ransomware
 */
export function ArpStatus() {
  const [arp, setArp] = useState<ArpData | null>(null);
  const [volumeName, setVolumeName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { t } = useTranslation();

  const loadArpStatus = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await client.queries.getArpStatus({});

      if (response.data) {
        const data = response.data as { volumeName?: string; arp?: ArpData; error?: string };
        if (data.error) {
          setError(data.error);
        } else if (data.arp) {
          setArp(data.arp);
          setVolumeName(data.volumeName || "");
        }
      } else if (response.errors) {
        setError(response.errors.map((e) => e.message).join(", "));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load ARP status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadArpStatus();
  }, []);

  if (loading) {
    return (
      <div className="protection-section">
        <h2>🛡️ {t("arpTitle")}</h2>
        <p className="loading">{t("loading")}</p>
      </div>
    );
  }

  // Fallback: ONTAP not connected
  if (error) {
    return (
      <div className="protection-section">
        <h2>🛡️ {t("arpTitle")}</h2>
        <div className="protection-info">
          <h3>📡 {t("arpOntapRequired")}</h3>
          <p>{t("arpOntapRequiredDesc")}</p>
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

  // --- Connected state: System Manager-inspired layout ---
  const getStateDotClass = (state: string): string => {
    switch (state) {
      case "enabled": return "status-dot-active";
      case "dry_run": return "status-dot-learning";
      case "paused": return "status-dot-warning";
      case "disabled": return "status-dot-disabled";
      default: return "status-dot-disabled";
    }
  };

  const getStateTitle = (state: string): string => {
    switch (state) {
      case "enabled": return t("arpStateEnabled");
      case "dry_run": return t("arpStateDryRun");
      case "paused": return t("arpStatePaused");
      case "disabled": return t("arpStateDisabled");
      default: return state;
    }
  };

  const getStateSubtitle = (state: string, dryRunStart: string): string => {
    switch (state) {
      case "enabled": return t("arpStateEnabled");
      case "dry_run": {
        const since = dryRunStart ? ` (${new Date(dryRunStart).toLocaleDateString()})` : "";
        return t("arpStateDryRun") + since;
      }
      case "paused": return t("arpStatePaused");
      case "disabled": return t("arpStateDisabled");
      default: return "";
    }
  };

  const getThreatColor = (probability: string): string => {
    switch (probability) {
      case "none": return "#22c55e";    // green
      case "low": return "#eab308";     // yellow
      case "moderate": return "#f97316"; // orange
      case "high": return "#ef4444";    // red
      default: return "#9ca3af";        // gray
    }
  };

  const getThreatLabel = (probability: string): string => {
    switch (probability) {
      case "none": return t("arpThreatNone");
      case "low": return t("arpThreatLow");
      case "moderate": return t("arpThreatModerate");
      case "high": return t("arpThreatHigh");
      default: return "Unknown";
    }
  };

  return (
    <div className="protection-section">
      <div className="protection-header">
        <h2>🛡️ {t("arpTitle")}</h2>
        {volumeName && (
          <span className="volume-badge" title="Source volume">
            {t("volume")}: {volumeName}
          </span>
        )}
        <button onClick={loadArpStatus} className="refresh-btn" title={t("refresh")}>
          ↻
        </button>
      </div>

      {arp && (
        <>
          {/* Primary status indicator — large, System Manager style */}
          <div className="status-indicator-large">
            <div className={`status-dot ${getStateDotClass(arp.state)}`} />
            <div className="status-label">
              <span className="status-title">{getStateTitle(arp.state)}</span>
              <span className="status-subtitle">
                {getStateSubtitle(arp.state, arp.dryRunStartTime)}
              </span>
            </div>
          </div>

          {/* Threat Assessment — color-coded banner */}
          <div
            className="threat-assessment"
            style={{ borderLeftColor: getThreatColor(arp.attackProbability) }}
          >
            <div className="threat-header">
              <span
                className="threat-indicator"
                style={{ backgroundColor: getThreatColor(arp.attackProbability) }}
              />
              <span className="threat-title">{t("arpThreatAssessment")}</span>
            </div>
            <p className="threat-level">{getThreatLabel(arp.attackProbability)}</p>
            {arp.attackProbability !== "none" && (
              <p className="threat-action">{t("arpCheckSnapshots")}</p>
            )}
          </div>

          {/* Protection Details */}
          <div className="protection-cards">
            <div className="protection-card">
              <div className="card-icon">🧠</div>
              <div className="card-content">
                <h3>{t("arpAiMlDetection")}</h3>
                <p>{arp.state === "enabled" ? t("arpActive") : arp.state === "dry_run" ? t("arpLearning") : t("arpInactive")}</p>
                <small>{t("arpMonitorsEntropy")}</small>
              </div>
            </div>

            <div className="protection-card">
              <div className="card-icon">📸</div>
              <div className="card-content">
                <h3>{t("arpAutoSnapshot")}</h3>
                <p>{arp.state === "enabled" ? t("arpArmed") : t("arpRequiresEnabled")}</p>
                <small>
                  {arp.state === "enabled"
                    ? t("arpLockedNote")
                    : t("arpEnableToActivate")}
                </small>
              </div>
            </div>

            <div className="protection-card">
              <div className="card-icon">🔐</div>
              <div className="card-content">
                <h3>{t("arpSnapshotTamperproof")}</h3>
                <p>{arp.state === "enabled" ? t("arpAutoLocked") : "—"}</p>
                <small>
                  {arp.state === "enabled"
                    ? t("arpLockedNote")
                    : t("arpTamperproofWhenEnabled")}
                </small>
              </div>
            </div>
          </div>

          {/* How it works — expandable */}
          <details className="arp-details">
            <summary>{t("arpHowItWorks")}</summary>
            <ul>
              <li>ONTAP monitors file behavior using machine learning (entropy analysis, access pattern anomaly detection)</li>
              <li>If ransomware-like activity is detected → automatic immutable Snapshot created</li>
              <li>ARP Snapshots visible in <strong>Snapshots</strong> tab (filter: "🛡️ ARP")</li>
              <li>FlexClone from ARP Snapshot → instant clean data restoration without downtime</li>
              <li>Tamperproof: ARP Snapshots are locked and cannot be deleted until expiry</li>
            </ul>
          </details>
        </>
      )}
    </div>
  );
}
