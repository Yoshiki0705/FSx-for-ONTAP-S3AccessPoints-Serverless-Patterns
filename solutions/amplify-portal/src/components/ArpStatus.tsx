import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";

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
        <h2>🛡️ Autonomous Ransomware Protection (ARP/AI)</h2>
        <p className="loading">Loading ARP status...</p>
      </div>
    );
  }

  // Fallback: ONTAP not connected
  if (error) {
    return (
      <div className="protection-section">
        <h2>🛡️ Autonomous Ransomware Protection (ARP/AI)</h2>
        <div className="protection-info">
          <h3>📡 ONTAP Connection Required</h3>
          <p>
            ARP/AI status is retrieved from the ONTAP management LIF via REST API.
            This section will display real-time ransomware protection status once
            the connection is configured.
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
      case "enabled": return "Active Protection";
      case "dry_run": return "Learning Mode";
      case "paused": return "Paused";
      case "disabled": return "Disabled";
      default: return state;
    }
  };

  const getStateSubtitle = (state: string, dryRunStart: string): string => {
    switch (state) {
      case "enabled": return "AI-driven monitoring active — detecting anomalous file behavior in real time";
      case "dry_run": {
        const since = dryRunStart ? ` since ${new Date(dryRunStart).toLocaleDateString()}` : "";
        return `Observing file access patterns${since}. No blocking — building behavioral baseline.`;
      }
      case "paused": return "Protection temporarily suspended by administrator";
      case "disabled": return "ARP/AI is not enabled on this volume";
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
      case "none": return "No Threats Detected";
      case "low": return "Low — Unusual Activity Observed";
      case "moderate": return "Moderate — Review Recommended";
      case "high": return "HIGH — Potential Attack In Progress";
      default: return "Unknown";
    }
  };

  return (
    <div className="protection-section">
      <div className="protection-header">
        <h2>🛡️ Autonomous Ransomware Protection (ARP/AI)</h2>
        {volumeName && (
          <span className="volume-badge" title="Source volume">
            Volume: {volumeName}
          </span>
        )}
        <button onClick={loadArpStatus} className="refresh-btn" title="Refresh ARP status">
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
              <span className="threat-title">Threat Assessment</span>
            </div>
            <p className="threat-level">{getThreatLabel(arp.attackProbability)}</p>
            {arp.attackProbability !== "none" && (
              <p className="threat-action">
                Check <strong>Snapshots</strong> section for ARP-triggered recovery points
              </p>
            )}
          </div>

          {/* Protection Details */}
          <div className="protection-cards">
            <div className="protection-card">
              <div className="card-icon">🧠</div>
              <div className="card-content">
                <h3>AI/ML Detection</h3>
                <p>{arp.state === "enabled" ? "Active" : arp.state === "dry_run" ? "Learning" : "Inactive"}</p>
                <small>Monitors file entropy, extension changes, access patterns</small>
              </div>
            </div>

            <div className="protection-card">
              <div className="card-icon">📸</div>
              <div className="card-content">
                <h3>Auto-Snapshot</h3>
                <p>{arp.state === "enabled" ? "Armed" : "Requires enabled state"}</p>
                <small>
                  {arp.state === "enabled"
                    ? "Immutable snapshot created on threat detection"
                    : "Enable ARP to activate automatic snapshot protection"}
                </small>
              </div>
            </div>

            <div className="protection-card">
              <div className="card-icon">🔐</div>
              <div className="card-content">
                <h3>Snapshot Tamperproof</h3>
                <p>{arp.state === "enabled" ? "Auto-locked" : "—"}</p>
                <small>
                  {arp.state === "enabled"
                    ? "ARP snapshots are locked — cannot be deleted even by admin"
                    : "ARP snapshots are tamperproof when ARP is enabled"}
                </small>
              </div>
            </div>
          </div>

          {/* How it works — expandable */}
          <details className="arp-details">
            <summary>How ARP/AI integrates with this portal</summary>
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
