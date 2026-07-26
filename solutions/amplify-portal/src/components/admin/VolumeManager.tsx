import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";

const client = generateClient<Schema>();

// Parse the JSON string response from generic dispatch endpoints
function parseResponse<T>(response: { data?: string | null }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === 'string' ? JSON.parse(response.data) : response.data;
  } catch { return null; }
}

interface Volume {
  name: string;
  uuid: string;
  sizeGiB: number;
  usedPercent: number;
  state: string;
  style: string;
  securityStyle: string;
  snaplockType: string;
}

/**
 * Volume Manager — List, create, resize, delete volumes.
 * System Manager-style table with capacity bar + action buttons.
 */
export function VolumeManager() {
  const { t } = useTranslation();
  const [volumes, setVolumes] = useState<Volume[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [actionResult, setActionResult] = useState<string | null>(null);

  // Create form state
  const [newName, setNewName] = useState("");
  const [newSize, setNewSize] = useState(100);
  const [newStyle, setNewStyle] = useState("unix");
  const [newSnaplockType, setNewSnaplockType] = useState("none");
  const [newRetentionDefault, setNewRetentionDefault] = useState("P30D");
  const [newRetentionMin, setNewRetentionMin] = useState("P1D");
  const [newRetentionMax, setNewRetentionMax] = useState("P365D");
  const [customRetentionNum, setCustomRetentionNum] = useState("30");
  const [customRetentionUnit, setCustomRetentionUnit] = useState("D");

  const loadVolumes = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await (client.queries as any).adminQuery({ action: "listVolumes", params: JSON.stringify({}) });
      const data = parseResponse<{ volumes?: Volume[]; error?: string }>(response);
      if (data) {
        if (data.error) setError(data.error);
        else setVolumes(data.volumes || []);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load volumes");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadVolumes(); }, []);

  const handleCreate = async () => {
    if (!newName) { setError(t("rmVolumeNameRequired")); return; }
    setActionResult(null);
    try {
      const response = await (client.mutations as any).adminMutation({ action: "createVolume", params: JSON.stringify({
        name: newName,
        sizeGiB: newSize,
        securityStyle: newStyle,
        snaplockType: newSnaplockType !== "none" ? newSnaplockType : undefined,
        retentionDefault: newSnaplockType !== "none" ? (newRetentionDefault === "custom" ? `P${customRetentionNum}${customRetentionUnit}` : newRetentionDefault) : undefined,
        retentionMin: newSnaplockType !== "none" ? newRetentionMin : undefined,
        retentionMax: newSnaplockType !== "none" ? newRetentionMax : undefined,
      }) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) {
          setActionResult(`${t("rmVolumeCreated")}: ${newName}`);
          setShowCreateForm(false);
          setNewName(""); setNewSize(100);
          loadVolumes();
        } else setError(data.error || "Create failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Create failed"); }
  };

  const handleResize = async (uuid: string, name: string) => {
    const input = prompt(t("rmResizePrompt"), "200");
    if (!input) return;
    const newSizeGiB = parseInt(input, 10);
    if (isNaN(newSizeGiB) || newSizeGiB <= 0) { setError("Invalid size"); return; }
    try {
      const response = await (client.mutations as any).adminMutation({ action: "resizeVolume", params: JSON.stringify({volumeUuid: uuid, newSizeGiB}) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) { setActionResult(`${name} → ${newSizeGiB} GiB`); loadVolumes(); }
        else setError(data.error || "Resize failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Resize failed"); }
  };

  const handleDelete = async (uuid: string, name: string) => {
    if (!confirm(t("rmDeleteConfirm").replace("{name}", name))) return;
    try {
      const response = await (client.mutations as any).adminMutation({ action: "deleteVolume", params: JSON.stringify({volumeUuid: uuid, volumeName: name, confirm: true}) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) { setActionResult(t("rmDeleted").replace("{name}", name)); loadVolumes(); }
        else setError(data.error || "Delete failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Delete failed"); }
  };

  if (loading) return <p className="loading">{t("loading")}</p>;

  return (
    <div className="admin-panel">
      <div className="panel-header">
        <h3>{t("rmVolumes")}</h3>
        <div className="panel-actions">
          <button onClick={() => setShowCreateForm(!showCreateForm)} className="btn-primary">
            + {t("rmCreateVolume")}
          </button>
          <button onClick={loadVolumes} className="refresh-btn">↻</button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}
      {actionResult && <div className="success-message">{actionResult}</div>}

      {showCreateForm && (
        <div className="create-form">
          <div className="form-row">
            <div className="form-group">
              <label>{t("rmVolumeName")}</label>
              <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)}
                placeholder="my_volume_01" />
              <small>{t("rmVolumeNameHint")}</small>
            </div>
            <div className="form-group">
              <label>{t("rmVolumeSize")} (GiB)</label>
              <input type="number" value={newSize} onChange={(e) => setNewSize(parseInt(e.target.value))}
                min={1} max={196608} />
            </div>
            <div className="form-group">
              <label>{t("rmSecurityStyle")}</label>
              <select value={newStyle} onChange={(e) => setNewStyle(e.target.value)}>
                <option value="unix">UNIX</option>
                <option value="ntfs">NTFS</option>
                <option value="mixed">Mixed</option>
              </select>
            </div>
          </div>
          {/* SnapLock configuration (optional) */}
          <div className="form-row">
            <div className="form-group">
              <label>{t("rmSnaplockType")}</label>
              <select value={newSnaplockType} onChange={(e) => setNewSnaplockType(e.target.value)}>
                <option value="none">None (standard volume)</option>
                <option value="enterprise">Enterprise (privileged delete)</option>
                <option value="compliance">Compliance (immutable)</option>
              </select>
              <small>{t("rmSnaplockTypeHint")}</small>
            </div>
            {newSnaplockType !== "none" && (
              <>
                <div className="form-group">
                  <label>{t("rmSnaplockRetentionDefault")}</label>
                  <select value={newRetentionDefault} onChange={(e) => setNewRetentionDefault(e.target.value)}>
                    <option value="P1D">1日</option>
                    <option value="P7D">7日</option>
                    <option value="P30D">30日 (1ヶ月)</option>
                    <option value="P90D">90日 (3ヶ月)</option>
                    <option value="P180D">180日 (6ヶ月)</option>
                    <option value="P365D">1年</option>
                    <option value="P730D">2年</option>
                    <option value="P1825D">5年</option>
                    <option value="P3650D">10年</option>
                    <option value="custom">カスタム...</option>
                  </select>
                  {newRetentionDefault === "custom" && (
                    <div className="form-row" style={{ marginTop: "0.3rem", gap: "0.5rem" }}>
                      <input type="number" value={customRetentionNum} onChange={(e) => setCustomRetentionNum(e.target.value)}
                        min={1} max={10950} style={{ width: "80px" }} />
                      <select value={customRetentionUnit} onChange={(e) => setCustomRetentionUnit(e.target.value)} style={{ width: "100px" }}>
                        <option value="D">日</option>
                        <option value="M">ヶ月</option>
                        <option value="Y">年</option>
                      </select>
                    </div>
                  )}
                  <small>{t("rmRetentionDefaultHint")} (1日〜30年)</small>
                </div>
                <div className="form-group">
                  <label>{t("rmSnaplockRetentionMin")}</label>
                  <select value={newRetentionMin} onChange={(e) => setNewRetentionMin(e.target.value)}>
                    <option value="P0D">制限なし</option>
                    <option value="P1D">1日</option>
                    <option value="P7D">7日</option>
                    <option value="P30D">30日</option>
                    <option value="P90D">90日</option>
                    <option value="P365D">1年</option>
                  </select>
                  <small>0日〜30年</small>
                </div>
                <div className="form-group">
                  <label>{t("rmSnaplockRetentionMax")}</label>
                  <select value={newRetentionMax} onChange={(e) => setNewRetentionMax(e.target.value)}>
                    <option value="P30D">30日</option>
                    <option value="P90D">90日</option>
                    <option value="P365D">1年</option>
                    <option value="P730D">2年</option>
                    <option value="P1825D">5年</option>
                    <option value="P3650D">10年</option>
                    <option value="P10950D">30年</option>
                  </select>
                  <small>1日〜30年</small>
                </div>
                <div className="info-message" style={{ marginTop: "0.5rem" }}>
                  ⚠️ {t("rmSnaplockRetentionWarning")}
                  {" "}
                  <a href="https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/how-snaplock-works.html" target="_blank" rel="noopener noreferrer" style={{ color: "#2563eb" }}>
                    📖 SnapLock documentation
                  </a>
                </div>
              </>
            )}
          </div>
          <button onClick={handleCreate} className="btn-primary">{t("rmCreate")}</button>
          <button onClick={() => setShowCreateForm(false)} className="btn-secondary">{t("cancel")}</button>
        </div>
      )}

      <table className="admin-table">
        <thead>
          <tr>
            <th>{t("rmVolumeName")}</th>
            <th>{t("rmVolumeSize")}</th>
            <th>{t("rmUsed")}</th>
            <th>{t("rmState")}</th>
            <th>{t("rmSecurityStyle")}</th>
            <th>{t("rmActions")}</th>
          </tr>
        </thead>
        <tbody>
          {volumes.map((vol) => (
            <tr key={vol.uuid}>
              <td className="vol-name">
                {vol.name}
                {vol.snaplockType !== "non_snaplock" && <span className="badge-lock">🔒</span>}
              </td>
              <td>{vol.sizeGiB} GiB</td>
              <td>
                <div className="capacity-bar">
                  <div className="capacity-fill" style={{ width: `${Math.min(vol.usedPercent, 100)}%`,
                    backgroundColor: vol.usedPercent > 90 ? "#ef4444" : vol.usedPercent > 75 ? "#f97316" : "#22c55e" }} />
                </div>
                <span className="capacity-label">{vol.usedPercent}%</span>
              </td>
              <td><span className={`state-badge state-${vol.state}`}>{vol.state}</span></td>
              <td>{vol.securityStyle}</td>
              <td className="action-cell">
                <button onClick={() => handleResize(vol.uuid, vol.name)} className="btn-sm"
                  title={t("rmResize")}>↔</button>
                <button onClick={() => handleDelete(vol.uuid, vol.name)} className="btn-sm btn-danger"
                  title={t("rmDelete")}>✕</button>
              </td>
            </tr>
          ))}
          {volumes.length === 0 && (
            <tr><td colSpan={6} className="empty-state">{t("rmNoVolumes")}</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
