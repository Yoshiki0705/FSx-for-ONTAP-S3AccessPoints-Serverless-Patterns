import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { dispatch } from "../lib/dispatch";
import { errorMessage, failureDiagnosis, unwrap } from "../lib/portalQuery";
import { useTranslation } from "../i18n";
import { useStorageAdmin } from "../hooks/useStorageAdmin";
import { ArpResponseActions } from "./ArpResponseActions";
import { OntapFailureNotice } from "./OntapFailureNotice";
import { VolumeSelector } from "./admin/VolumeSelector";

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
  const isStorageAdmin = useStorageAdmin();
  // Which volume this page describes. Empty means "the configured one", which is what
  // the handler falls back to and what a reader without the storage-admin group gets.
  //
  // Before this, the page could only ever describe that one volume: it showed the name
  // as a fixed badge, so protection turned on anywhere else looked like protection that
  // had not taken effect.
  const [selectedVolume, setSelectedVolume] = useState("");

  const {
    data,
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["protection", "getArpStatus", selectedVolume || null],
    queryFn: () =>
      unwrap<{ volumeName?: string; arp?: ArpData }>(
        dispatch("protectionQuery", {
          action: "getArpStatus",
          params: selectedVolume ? { volumeName: selectedVolume } : {},
        }),
      ),
  });

  const arp = data?.arp ?? null;
  const volumeName = data?.volumeName ?? "";
  const error = errorMessage(queryError, "Failed to load ARP status");

  // Only while there is nothing to show. `isPending` is true again for every new query
  // key, so returning the loading screen on it replaced the whole page -- including the
  // volume selector -- and the selector came back with its state reset. The selection
  // survived in the parent, so the badge was right while the dropdown read "select a
  // volume": one control disagreeing with another about the same fact.
  if (loading && !data) {
    return (
      <div className="protection-section">
        <h2>🛡️ {t("arpTitle")}</h2>
        <p className="loading">{t("loading")}</p>
      </div>
    );
  }

  // No ARP data. Which of the five reasons it was is the handler's to say.
  if (error) {
    return (
      <div className="protection-section">
        <h2>🛡️ {t("arpTitle")}</h2>
        <OntapFailureNotice error={error} {...failureDiagnosis(queryError)} />
      </div>
    );
  }

  // --- Connected state: System Manager-inspired layout ---
  const getStateDotClass = (state: string): string => {
    switch (state) {
      case "enabled": return "status-dot-active";
      case "dry_run": return "status-dot-learning";
      case "paused": return "status-dot-warning";
      // Measured on 9.18.1P3D1: turning protection off leaves the volume in
      // `disable_in_progress` for minutes. It is not off yet, so it does not get the
      // "off" dot -- and it fell through to the default before, which said it was.
      case "disable_in_progress": return "status-dot-warning";
      case "disabled": return "status-dot-disabled";
      default: return "status-dot-disabled";
    }
  };

  const getStateTitle = (state: string): string => {
    switch (state) {
      case "enabled": return t("arpStateEnabled");
      case "dry_run": return t("arpStateDryRun");
      case "paused": return t("arpStatePaused");
      case "disable_in_progress": return t("arpStateDisabling");
      case "disabled": return t("arpStateDisabled");
      // Not `state`: an ONTAP token shown verbatim to a reader is not an answer, and
      // this is the branch a value ONTAP adds later would arrive in.
      default: return t("arpStateUnknown").replace("{state}", state);
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
      case "disable_in_progress": return t("arpStateDisablingHint");
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
        {/* The badge stays whichever way the volume was chosen: it comes from the
            response, so it names the volume the figures below actually describe. The
            selector alone would not -- it reads "select a volume" until something is
            picked, while the page is already showing the configured one. */}
        {volumeName && (
          <span className="volume-badge" title={t("srcVolumeTitle")}>
            {t("volume")}: {volumeName}
          </span>
        )}
        {isStorageAdmin === true && (
          <VolumeSelector
            label={t("rmSelectVolume")}
            onSelect={(vol) => setSelectedVolume(vol.name)}
          />
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
