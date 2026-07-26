import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";
import { VolumeSelector } from "./VolumeSelector";

const client = generateClient<Schema>();

// Parse the JSON string response from generic dispatch endpoints
function parseResponse<T>(response: { data?: string | null }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === 'string' ? JSON.parse(response.data) : response.data;
  } catch { return null; }
}

interface SnapshotPolicy {
  name: string;
  uuid: string;
  enabled: boolean;
  comment: string;
  scheduleCount: number;
  schedules: { schedule: string; count: number; prefix: string; retentionPeriod: string }[];
}

interface LockingConfig {
  volumeName: string;
  snapshotLockingEnabled: boolean;
  snapshotPolicy: string;
  lockedSnapshotCount: number;
  totalSnapshotCount: number;
}

/**
 * Snapshot Administration — Policy management, Tamperproof locking, Schedule config.
 *
 * System Manager equivalent: Storage > Volumes > Snapshot Policies + Tamperproof
 *
 * Features:
 * - List/create snapshot policies (with schedules + retention periods)
 * - Enable tamperproof snapshot locking per volume
 * - Lock individual snapshots with retention (cannot delete until expiry)
 * - Assign policies to volumes
 * - View locking status per volume
 */
export function SnapshotAdminManager() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<"policies" | "tamperproof">("policies");
  const [policies, setPolicies] = useState<SnapshotPolicy[]>([]);
  const [lockConfig, setLockConfig] = useState<LockingConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [showCreatePolicy, setShowCreatePolicy] = useState(false);
  const [volumeUuid, setVolumeUuid] = useState("");

  // Policy form state
  const [policyName, setPolicyName] = useState("");
  const [policyComment, setPolicyComment] = useState("");
  const [policySchedule, setPolicySchedule] = useState("daily");
  const [policyCount, setPolicyCount] = useState(7);
  const [policyRetention, setPolicyRetention] = useState("");

  const clearResult = () => setTimeout(() => setResult(null), 4000);

  const loadPolicies = async () => {
    setLoading(true); setError(null);
    try {
      const response = await (client.queries as any).adminQuery({ action: "listSnapshotPolicies", params: JSON.stringify({}) });
      const data = parseResponse<{ policies?: SnapshotPolicy[]; error?: string }>(response);
      if (data) {
        if (data.error) setError(data.error);
        else setPolicies(data.policies || []);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Load failed"); }
    finally { setLoading(false); }
  };

  const loadLockingStatus = async () => {
    if (!volumeUuid) return;
    setLoading(true); setError(null);
    try {
      const response = await (client.queries as any).adminQuery({ action: "getSnapshotLockingStatus", params: JSON.stringify({volumeUuid}) });
      const data = parseResponse<{ config?: LockingConfig; error?: string }>(response);
      if (data) {
        if (data.error) setError(data.error);
        else setLockConfig(data.config || null);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Load failed"); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    if (activeTab === "policies") loadPolicies();
  }, [activeTab]);

  const handleCreatePolicy = async () => {
    if (!policyName) { setError(t("rmSnapPolicyNameRequired")); return; }
    try {
      const response = await (client.mutations as any).adminMutation({ action: "createSnapshotPolicy", params: JSON.stringify({
        name: policyName, comment: policyComment,
        schedules: JSON.stringify([{ schedule: policySchedule, count: policyCount, retentionPeriod: policyRetention || undefined }]),
      }) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) {
          setResult(`${t("rmSnapPolicyCreated")}: ${policyName}`); clearResult();
          setShowCreatePolicy(false); setPolicyName(""); setPolicyComment("");
          loadPolicies();
        } else setError(data.error || "Failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  const handleEnableLocking = async () => {
    if (!volumeUuid) return;
    // Multi-step safety confirmation — enabling locking on a Compliance volume is IRREVERSIBLE
    const confirmed = window.prompt(
      "⚠️ Tamperproof Snapshot ロックを有効化しますか？\n\n" +
      "【重要】この操作は Compliance ボリュームでは取り消せません。\n" +
      "有効化後にロックされた Snapshot は、保持期間が満了するまで\n" +
      "誰も削除できなくなります（root / fsxadmin 含む）。\n\n" +
      "※ この操作はボリューム上の「ロック機能」を有効にするだけです。\n" +
      "  個別 Snapshot のロックは別途「Lock」ボタンから保持期間を指定して行います。\n\n" +
      "続行するには ENABLE と入力してください:",
      ""
    );
    if (confirmed !== "ENABLE") {
      setError("有効化がキャンセルされました（ENABLE と入力する必要があります）");
      return;
    }
    try {
      const response = await (client.mutations as any).adminMutation({ action: "enableSnapshotLocking", params: JSON.stringify({volumeUuid, enabled: true}) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) { setResult(t("rmSnapLockingEnabled")); clearResult(); loadLockingStatus(); }
        else setError(data.error || "Failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  if (loading && activeTab === "policies" && policies.length === 0) return <p className="loading">{t("loading")}</p>;

  return (
    <div className="admin-panel">
      <div className="panel-header">
        <h3>{t("rmSnapshotAdmin")}</h3>
        <div className="panel-actions">
          <button onClick={() => setActiveTab("policies")} className={activeTab === "policies" ? "btn-primary" : "btn-secondary"}>
            {t("rmSnapPolicies")}
          </button>
          <button onClick={() => setActiveTab("tamperproof")} className={activeTab === "tamperproof" ? "btn-primary" : "btn-secondary"}>
            {t("rmSnapTamperproof")}
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}
      {result && <div className="success-message">{result}</div>}

      {activeTab === "policies" && (
        <>
          <div className="panel-actions" style={{ marginBottom: "1rem" }}>
            <button onClick={() => setShowCreatePolicy(!showCreatePolicy)} className="btn-primary">
              + {t("rmSnapCreatePolicy")}
            </button>
            <button onClick={loadPolicies} className="refresh-btn">↻</button>
          </div>

          {showCreatePolicy && (
            <div className="create-form">
              <div className="form-row">
                <div className="form-group">
                  <label>{t("rmSnapPolicyName")}</label>
                  <input type="text" value={policyName} onChange={(e) => setPolicyName(e.target.value)} placeholder="my_policy" />
                </div>
                <div className="form-group">
                  <label>{t("rmSnapSchedule")}</label>
                  <select value={policySchedule} onChange={(e) => setPolicySchedule(e.target.value)}>
                    <option value="5min">5min</option>
                    <option value="8hour">8hour</option>
                    <option value="hourly">Hourly</option>
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>{t("rmSnapCount")}</label>
                  <input type="number" value={policyCount} onChange={(e) => setPolicyCount(parseInt(e.target.value))} min={1} max={1023} />
                </div>
                <div className="form-group">
                  <label>{t("rmSnapRetention")} (ISO)</label>
                  <input type="text" value={policyRetention} onChange={(e) => setPolicyRetention(e.target.value)} placeholder="P30D (optional)" />
                  <small>{t("rmSnapRetentionHint")}</small>
                </div>
              </div>
              <div className="form-group">
                <label>{t("rmShareComment")}</label>
                <input type="text" value={policyComment} onChange={(e) => setPolicyComment(e.target.value)} placeholder="Optional" />
              </div>
              <button onClick={handleCreatePolicy} className="btn-primary">{t("rmCreate")}</button>
              <button onClick={() => setShowCreatePolicy(false)} className="btn-secondary">{t("cancel")}</button>
            </div>
          )}

          <table className="admin-table">
            <thead><tr><th>{t("rmSnapPolicyName")}</th><th>{t("rmSnapSchedules")}</th><th>{t("rmState")}</th><th>{t("rmShareComment")}</th></tr></thead>
            <tbody>
              {policies.map((p) => (
                <tr key={p.uuid}>
                  <td>{p.name}</td>
                  <td>
                    {p.schedules.map((s, i) => (
                      <div key={i}>
                        <code>{s.schedule}</code> × {s.count}
                        {s.retentionPeriod && <span className="badge"> 🔒 {s.retentionPeriod}</span>}
                      </div>
                    ))}
                  </td>
                  <td><span className={`state-badge state-${p.enabled ? "online" : "offline"}`}>{p.enabled ? "Enabled" : "Disabled"}</span></td>
                  <td>{p.comment || "—"}</td>
                </tr>
              ))}
              {policies.length === 0 && <tr><td colSpan={4} className="empty-state">{t("rmSnapNoPolicies")}</td></tr>}
            </tbody>
          </table>
        </>
      )}

      {activeTab === "tamperproof" && (
        <>
          <p style={{ marginBottom: "1rem" }}>{t("rmSnapTamperproofDesc")}</p>

          <div className="create-form">
            <VolumeSelector
              label={t("rmSnapSelectVolume")}
              showUuid
              onSelect={(vol) => { setVolumeUuid(vol.uuid); }}
            />
            <button onClick={loadLockingStatus} className="btn-primary" disabled={!volumeUuid} style={{ marginTop: "0.75rem" }}>{t("rmSnapCheckStatus")}</button>
          </div>

          {lockConfig && (
            <div className="detail-grid" style={{ marginTop: "1rem" }}>
              <div className="detail-card">
                <div className="detail-label">{t("rmVolumeName")}</div>
                <div className="detail-value">{lockConfig.volumeName}</div>
              </div>
              <div className="detail-card">
                <div className="detail-label">{t("rmSnapLockingState")}</div>
                <div className={`detail-value ${lockConfig.snapshotLockingEnabled ? "text-success" : ""}`}>
                  {lockConfig.snapshotLockingEnabled ? "🔒 Enabled" : "— Disabled"}
                </div>
              </div>
              <div className="detail-card">
                <div className="detail-label">{t("rmSnapLockedCount")}</div>
                <div className="detail-value">{lockConfig.lockedSnapshotCount} / {lockConfig.totalSnapshotCount}</div>
              </div>
              <div className="detail-card">
                <div className="detail-label">{t("rmSnapPolicy")}</div>
                <div className="detail-value">{lockConfig.snapshotPolicy || "—"}</div>
              </div>

              {!lockConfig.snapshotLockingEnabled && (
                <button onClick={handleEnableLocking} className="btn-primary" style={{ marginTop: "1rem" }}>
                  🔒 {t("rmSnapEnableLocking")}
                </button>
              )}
            </div>
          )}

          <details style={{ marginTop: "1.5rem" }}>
            <summary>{t("rmSnapTamperproofHow")}</summary>
            <ul>
              <li>{t("rmSnapTamperproofStep1")}</li>
              <li>{t("rmSnapTamperproofStep2")}</li>
              <li>{t("rmSnapTamperproofStep3")}</li>
              <li>{t("rmSnapTamperproofStep4")}</li>
            </ul>
          </details>
        </>
      )}
    </div>
  );
}
