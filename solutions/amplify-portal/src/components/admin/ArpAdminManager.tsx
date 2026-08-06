import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";
import { parseResponse } from "../../utils/parseResponse";

const client = generateClient<Schema>();

// Parse the JSON string response from generic dispatch endpoints

interface ArpVolume {
  name: string;
  uuid: string;
  state: string;
  attackProbability: string;
  dryRunStartTime: string | null;
  surgeAsNormal: boolean;
  volumeType: string; // "NAS" or "SAN"
  sizeGiB: number;
}

interface ArpSummary {
  total: number;
  enabled: number;
  learning: number;
  disabled: number;
}

/**
 * A file ONTAP flagged as a possible ransomware indicator.
 *
 * Fields match what the suspects table renders. `filePath` and `fileType` are
 * optional because the table already falls back to an em dash for each.
 */
interface ArpSuspect {
  filePath?: string;
  fileType?: string;
  suspectTime: string;
}

/**
 * ARP/AI Administration Manager — Full ransomware protection management.
 *
 * Supports:
 * - ARP/AI (ONTAP 9.16+): Direct enable, no learning period (AI pre-trained)
 * - Classic ARP (pre-9.16): dry_run → enabled transition (30-day learning)
 * - ARP for SAN (ONTAP 9.17.1+): Entropy-based detection on LUN volumes
 *
 * Operations:
 * - View all volumes with ARP state (NAS + SAN tagged)
 * - Enable/disable/pause ARP per volume
 * - Start learning mode (dry_run) for classic ARP
 * - Bulk enable across multiple volumes
 * - View suspect files (NAS) or entropy spikes (SAN)
 * - Clear false positives
 * - Mark surge as normal activity
 *
 * System Manager equivalent: Storage > Volumes > Anti-Ransomware
 */
export function ArpAdminManager() {
  const { t } = useTranslation();
  const [volumes, setVolumes] = useState<ArpVolume[]>([]);
  const [summary, setSummary] = useState<ArpSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [selectedVolume, setSelectedVolume] = useState<ArpVolume | null>(null);
  const [suspects, setSuspects] = useState<ArpSuspect[]>([]);
  const [showBulkEnable, setShowBulkEnable] = useState(false);
  const [bulkState, setBulkState] = useState<"enabled" | "dry_run">("enabled");

  const clearResult = () => setTimeout(() => setResult(null), 4000);

  const loadVolumes = async () => {
    setLoading(true); setError(null);
    try {
      const response = await client.queries.adminQuery({ action: "listArpVolumes", params: JSON.stringify({}) });
      const data = parseResponse<{ volumes?: ArpVolume[]; summary?: ArpSummary; error?: string }>(response);
      if (data) {
        if (data.error) setError(data.error);
        else { setVolumes(data.volumes || []); setSummary(data.summary || null); }
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Load failed"); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadVolumes(); }, []);

  const handleStateChange = async (vol: ArpVolume, newState: string) => {
    const confirmMsg = newState === "disabled"
      ? `${t("rmArpDisableWarning")}: ${vol.name}?`
      : `${t("rmArpChangeState")} ${vol.name} → ${newState}?`;
    if (!window.confirm(confirmMsg)) return;

    setError(null);
    try {
      const response = await client.mutations.adminMutation({ action: "updateArpStateAdmin", params: JSON.stringify({
        volumeUuid: vol.uuid, state: newState,
      }) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) {
          setResult(`${vol.name} → ${newState}`); clearResult(); loadVolumes();
        } else setError(data.error || "Failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  const handleViewSuspects = async (vol: ArpVolume) => {
    setSelectedVolume(vol); setSuspects([]);
    try {
      const response = await client.queries.adminQuery({ action: "getArpSuspectsAdmin", params: JSON.stringify({volumeUuid: vol.uuid}) });
      const data = parseResponse<{ suspects?: ArpSuspect[]; error?: string }>(response);
      if (data) {
        if (data.error) setError(data.error);
        else setSuspects(data.suspects || []);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  const handleClearSuspects = async () => {
    if (!selectedVolume) return;
    if (!window.confirm(t("rmArpClearSuspectsConfirm"))) return;
    try {
      const response = await client.mutations.adminMutation({ action: "clearArpSuspects", params: JSON.stringify({volumeUuid: selectedVolume.uuid}) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) { setResult(t("rmArpSuspectsCleared")); clearResult(); setSuspects([]); loadVolumes(); }
        else setError(data.error || "Failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  const handleSurgeAsNormal = async (vol: ArpVolume) => {
    if (!window.confirm(t("rmArpSurgeConfirm"))) return;
    try {
      const response = await client.mutations.adminMutation({ action: "updateArpSurgeParams", params: JSON.stringify({
        volumeUuid: vol.uuid, surgeAsNormal: true,
      }) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) { setResult(t("rmArpSurgeMarked")); clearResult(); loadVolumes(); }
        else setError(data.error || "Failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  const handleBulkEnable = async () => {
    const unprotected = volumes.filter(v => v.state === "disabled").map(v => v.uuid);
    if (unprotected.length === 0) { setError(t("rmArpAllProtected")); return; }
    if (!window.confirm(`${t("rmArpBulkConfirm")} ${unprotected.length} ${t("rmArpVolumesTo")} ${bulkState}?`)) return;

    try {
      const response = await client.mutations.adminMutation({ action: "enableArpBulk", params: JSON.stringify({
        volumeUuids: unprotected, state: bulkState,
      }) });
      const data = parseResponse<{ successCount?: number; totalCount?: number; error?: string }>(response);
      if (data) {
        setResult(`${data.successCount}/${data.totalCount} ${t("rmArpBulkDone")}`);
        clearResult(); setShowBulkEnable(false); loadVolumes();
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  const getStateColor = (state: string) => {
    switch (state) {
      case "enabled": return "#22c55e";
      case "dry_run": return "#3b82f6";
      case "paused": return "#f97316";
      case "disabled": return "#9ca3af";
      default: return "#9ca3af";
    }
  };

  const getStateLabel = (state: string) => {
    switch (state) {
      case "enabled": return t("stateEnabled");
      case "dry_run": return t("rmArpLearning");
      case "paused": return t("rmArpPaused");
      case "disabled": return t("stateDisabled");
      default: return state;
    }
  };

  if (loading) return <p className="loading">{t("loading")}</p>;

  return (
    <div className="admin-panel">
      <div className="panel-header">
        <h3>{t("rmArpAdmin")}</h3>
        <div className="panel-actions">
          <button onClick={() => setShowBulkEnable(!showBulkEnable)} className="btn-primary">
            {t("rmArpBulkEnable")}
          </button>
          <button onClick={loadVolumes} className="refresh-btn">↻</button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}
      {result && <div className="success-message">{result}</div>}

      {/* Summary cards */}
      {summary && (
        <div className="form-row" style={{ marginBottom: "1.5rem" }}>
          <div className="form-group" style={{ textAlign: "center", padding: "0.75rem", border: "1px solid #22c55e", borderRadius: "8px" }}>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "#22c55e" }}>{summary.enabled}</div>
            <div>{t("stateEnabled")}</div>
          </div>
          <div className="form-group" style={{ textAlign: "center", padding: "0.75rem", border: "1px solid #3b82f6", borderRadius: "8px" }}>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "#3b82f6" }}>{summary.learning}</div>
            <div>{t("rmArpLearning")}</div>
          </div>
          <div className="form-group" style={{ textAlign: "center", padding: "0.75rem", border: "1px solid #9ca3af", borderRadius: "8px" }}>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "#9ca3af" }}>{summary.disabled}</div>
            <div>{t("stateDisabled")}</div>
          </div>
          <div className="form-group" style={{ textAlign: "center", padding: "0.75rem", border: "1px solid var(--border-color)", borderRadius: "8px" }}>
            <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>{summary.total}</div>
            <div>{t("rmArpTotal")}</div>
          </div>
        </div>
      )}

      {/* Bulk enable */}
      {showBulkEnable && (
        <div className="create-form">
          <p>{t("rmArpBulkDesc")}</p>
          <div className="form-row">
            <div className="form-group">
              <label>{t("rmArpTargetState")}</label>
              <select value={bulkState} onChange={(e) => setBulkState(e.target.value as "enabled" | "dry_run")}>
                <option value="enabled">{t("stateEnabled")} (ARP/AI — {t("rmArpNoLearning")})</option>
                <option value="dry_run">{t("rmArpLearning")} ({t("rmArpClassic30Day")})</option>
              </select>
            </div>
          </div>
          <button onClick={handleBulkEnable} className="btn-primary">{t("rmArpBulkEnable")}</button>
          <button onClick={() => setShowBulkEnable(false)} className="btn-secondary">{t("cancel")}</button>
        </div>
      )}

      {/* Suspects panel */}
      {selectedVolume && (
        <div className="create-form" style={{ marginBottom: "1rem" }}>
          <h4>{t("rmArpSuspects")}: {selectedVolume.name}</h4>
          {suspects.length === 0 ? (
            <p className="empty-state">{t("rmArpNoSuspects")}</p>
          ) : (
            <>
              <table className="admin-table">
                <thead><tr><th>{t("rmArpFilePath")}</th><th>{t("rmArpFileType")}</th><th>{t("rmArpSuspectTime")}</th></tr></thead>
                <tbody>
                  {suspects.map((s, i) => (
                    <tr key={i}><td>{s.filePath || "—"}</td><td>{s.fileType || "—"}</td><td>{s.suspectTime}</td></tr>
                  ))}
                </tbody>
              </table>
              <button onClick={handleClearSuspects} className="btn-warning">{t("rmArpClearSuspects")}</button>
            </>
          )}
          <button onClick={() => setSelectedVolume(null)} className="btn-secondary">{t("rmBackToList")}</button>
        </div>
      )}

      {/* Volume table */}
      <table className="admin-table">
        <thead>
          <tr>
            <th>{t("rmVolumeName")}</th>
            <th>{t("rmArpVolumeType")}</th>
            <th>{t("rmArpState")}</th>
            <th>{t("rmArpThreat")}</th>
            <th>{t("rmActions")}</th>
          </tr>
        </thead>
        <tbody>
          {volumes.map((vol) => (
            <tr key={vol.uuid}>
              <td>{vol.name} <small>({vol.sizeGiB} GiB)</small></td>
              <td><span className="badge">{vol.volumeType}</span></td>
              <td>
                <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: getStateColor(vol.state) }} />
                  {getStateLabel(vol.state)}
                </span>
                {vol.state === "dry_run" && vol.dryRunStartTime && (
                  <small style={{ display: "block", color: "#6b7280" }}>
                    {t("rmArpSince")} {new Date(vol.dryRunStartTime).toLocaleDateString()}
                  </small>
                )}
              </td>
              <td>
                {vol.attackProbability !== "none" && (
                  <span className="state-badge" style={{ backgroundColor: vol.attackProbability === "high" ? "#ef4444" : "#f97316", color: "#fff" }}>
                    {vol.attackProbability}
                  </span>
                )}
                {vol.attackProbability === "none" && "—"}
              </td>
              <td className="action-cell">
                {vol.state === "disabled" && (
                  <>
                    <button onClick={() => handleStateChange(vol, "enabled")} className="btn-sm" title={t("arpModeNoLearning")}>AI</button>
                    <button onClick={() => handleStateChange(vol, "dry_run")} className="btn-sm" title={t("arpModeClassic")}>Learn</button>
                  </>
                )}
                {vol.state === "dry_run" && (
                  <button onClick={() => handleStateChange(vol, "enabled")} className="btn-sm" title={t("arpActivate")}>{t("rmArpActivate")}</button>
                )}
                {vol.state === "enabled" && (
                  <button onClick={() => handleStateChange(vol, "paused")} className="btn-sm" title={t("arpPause")}>⏸</button>
                )}
                {vol.state === "paused" && (
                  <button onClick={() => handleStateChange(vol, "enabled")} className="btn-sm" title={t("arpResume")}>▶</button>
                )}
                {vol.state !== "disabled" && (
                  <button onClick={() => handleStateChange(vol, "disabled")} className="btn-sm btn-danger" title={t("arpDisable")}>✕</button>
                )}
                {vol.attackProbability !== "none" && (
                  <button onClick={() => handleViewSuspects(vol)} className="btn-sm" title={t("arpViewSuspects")}>🔍</button>
                )}
                {vol.state === "enabled" && (
                  <button onClick={() => handleSurgeAsNormal(vol)} className="btn-sm" title={t("arpMarkSurgeNormal")}>📊</button>
                )}
              </td>
            </tr>
          ))}
          {volumes.length === 0 && <tr><td colSpan={5} className="empty-state">{t("rmNoVolumes")}</td></tr>}
        </tbody>
      </table>

      {/* Info panel — ARP mode explanation */}
      <details className="arp-details" style={{ marginTop: "1rem" }}>
        <summary>{t("rmArpModeExplanation")}</summary>
        <ul>
          <li><strong>ARP/AI (ONTAP 9.16+):</strong> {t("rmArpAiDesc")}</li>
          <li><strong>{t("rmArpClassic")}:</strong> {t("rmArpClassicDesc")}</li>
          <li><strong>ARP for SAN (ONTAP 9.17.1+):</strong> {t("rmArpSanDesc")}</li>
        </ul>
      </details>
    </div>
  );
}
