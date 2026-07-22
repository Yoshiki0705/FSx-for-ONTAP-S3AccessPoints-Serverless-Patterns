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
 * Queries ONTAP REST API via VPC Lambda to display real-time
 * Autonomous Ransomware Protection status for the configured volume.
 *
 * Architecture:
 *   AppSync getArpStatus → VPC Lambda → ONTAP REST API
 *   GET /api/storage/volumes?fields=anti_ransomware
 *
 * ARP states:
 *   - disabled: ARP not enabled on this volume
 *   - dry_run: Learning mode (observing patterns, no blocking)
 *   - enabled: Active protection (detecting + auto-snapshot on threat)
 *   - paused: Temporarily paused by admin
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

  const getStateIcon = (state: string): string => {
    switch (state) {
      case "enabled": return "✅";
      case "dry_run": return "🔄";
      case "paused": return "⏸️";
      case "disabled": return "⚠️";
      default: return "❓";
    }
  };

  const getStateLabel = (state: string): string => {
    switch (state) {
      case "enabled": return "Active — AI-driven protection enabled";
      case "dry_run": return "Learning mode — observing file patterns";
      case "paused": return "Paused — temporarily suspended by admin";
      case "disabled": return "Disabled — not configured on this volume";
      default: return state;
    }
  };

  const getStateBadgeClass = (state: string): string => {
    switch (state) {
      case "enabled": return "status-ok";
      case "dry_run": return "status-learning";
      case "paused": return "status-warning";
      case "disabled": return "status-disabled";
      default: return "";
    }
  };

  const getThreatIcon = (probability: string): string => {
    switch (probability) {
      case "none": return "🟢";
      case "low": return "🟡";
      case "moderate": return "🟠";
      case "high": return "🔴";
      default: return "⚪";
    }
  };

  const getThreatLabel = (probability: string): string => {
    switch (probability) {
      case "none": return "No threats detected";
      case "low": return "Low probability activity detected";
      case "moderate": return "Moderate probability — review recommended";
      case "high": return "HIGH — Potential ransomware attack in progress";
      default: return "Unknown";
    }
  };

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
            <li>The <strong>ListSnapshots Lambda</strong> must be deployed in a VPC subnet
                that can reach the management LIF</li>
            <li>Environment variables required: <code>ONTAP_MGMT_IP</code>,
                <code>ONTAP_SECRET_NAME</code>, <code>VOLUME_NAME</code>, <code>SVM_NAME</code></li>
            <li>Security group must allow outbound TCP/443 to the management LIF IP</li>
          </ul>
          <p className="integration-note">
            <strong>DemoMode note</strong>: File browsing, AI processing, and upload work without
            ONTAP connectivity. Only Data Protection features (ARP, Snapshots, SnapLock) require
            the VPC Lambda → ONTAP REST API path.
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

      <p className="section-description">
        ONTAP ARP/AI monitors file activity patterns using machine learning and detects
        anomalous behavior indicative of ransomware attacks. When suspicious activity is
        detected, an automatic Snapshot is created to preserve clean data.
      </p>

      {arp && (
        <>
          <div className="protection-cards">
            <div className={`protection-card ${getStateBadgeClass(arp.state)}`}>
              <div className="card-icon">{getStateIcon(arp.state)}</div>
              <div className="card-content">
                <h3>ARP State</h3>
                <p>{getStateLabel(arp.state)}</p>
                {arp.state === "dry_run" && arp.dryRunStartTime && (
                  <small>Learning since: {new Date(arp.dryRunStartTime).toLocaleDateString()}</small>
                )}
              </div>
            </div>

            <div className="protection-card">
              <div className="card-icon">{getThreatIcon(arp.attackProbability)}</div>
              <div className="card-content">
                <h3>Threat Level</h3>
                <p>{getThreatLabel(arp.attackProbability)}</p>
                {arp.attackProbability !== "none" && (
                  <small>Check the Snapshots section for ARP-triggered recovery points</small>
                )}
              </div>
            </div>

            <div className="protection-card">
              <div className="card-icon">📸</div>
              <div className="card-content">
                <h3>Auto-Snapshot on Threat</h3>
                <p>{arp.state === "enabled" ? "Active" : "Requires ARP enabled state"}</p>
                <small>
                  {arp.state === "enabled"
                    ? "Immutable Snapshot created automatically when threats are detected"
                    : "Enable ARP to activate automatic Snapshot protection"}
                </small>
              </div>
            </div>
          </div>

          <div className="protection-info">
            <h3>How ARP/AI integrates with this portal</h3>
            <ul>
              <li>ONTAP monitors file entropy, extension changes, and access patterns via AI/ML</li>
              <li>If ransomware-like behavior is detected, ARP creates an immutable Snapshot</li>
              <li>The <strong>Snapshots</strong> section shows all recovery points (including ARP-triggered ones)</li>
              <li>FlexClone from an ARP Snapshot restores clean data without downtime</li>
              <li><strong>Tamperproof</strong>: ARP Snapshots are locked — they cannot be deleted even by admin</li>
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
