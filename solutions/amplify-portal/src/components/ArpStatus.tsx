import { useQuery } from "@tanstack/react-query";
import { dispatch } from "../lib/dispatch";
import { errorMessage, unwrap } from "../lib/portalQuery";
import { useTranslation } from "../i18n";
import { ArpResponseActions } from "./ArpResponseActions";

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
  const { t } = useTranslation();

  const {
    data,
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["protection", "getArpStatus"],
    queryFn: () =>
      unwrap<{ volumeName?: string; arp?: ArpData }>(
        dispatch("protectionQuery", { action: "getArpStatus" }),
      ),
  });

  const arp = data?.arp ?? null;
  const volumeName = data?.volumeName ?? "";
  const error = errorMessage(queryError, "Failed to load ARP status");

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
          <span className="volume-badge" title={t("srcVolumeTitle")}>
            {t("volume")}: {volumeName}
          </span>
        )}
        <button onClick={() => void refetch()} className="refresh-btn" title={t("refresh")}>
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
              <li>{t("arpDetail1")}</li>
              <li>{t("arpDetail2")}</li>
              <li>{t("arpDetail3")}</li>
              <li>{t("arpDetail4")}</li>
              <li>{t("arpDetail5")}</li>
            </ul>
          </details>

          {/* ARP Response Actions — visible for storage-admin users */}
          <ArpResponseActions
            threatLevel={arp.attackProbability}
            volumeName={volumeName}
          />
        </>
      )}
    </div>
  );
}
