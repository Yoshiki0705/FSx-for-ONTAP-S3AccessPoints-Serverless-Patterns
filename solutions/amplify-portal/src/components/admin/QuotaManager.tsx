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

interface QuotaRule {
  uuid: string;
  type: string;
  qtreeName?: string;
  userName?: string;
  groupName?: string;
  spaceHardLimitGiB: number;
  spaceSoftLimitGiB: number;
  filesHardLimit: number;
}

interface QuotaUsage {
  target: string;
  type: string;
  spaceUsedGiB: number;
  spaceHardLimitGiB: number;
  filesUsed: number;
  filesHardLimit: number;
}

export function QuotaManager() {
  const { t } = useTranslation();
  const [rules, setRules] = useState<QuotaRule[]>([]);
  const [usage, setUsage] = useState<QuotaUsage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"rules" | "report">("rules");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [volumeName, setVolumeName] = useState("");

  // Create form state
  const [newType, setNewType] = useState<"tree" | "user" | "group">("tree");
  const [newQtreeName, setNewQtreeName] = useState("");
  const [newUserName, setNewUserName] = useState("");
  const [newGroupName, setNewGroupName] = useState("");
  const [newSpaceHard, setNewSpaceHard] = useState(100);
  const [newSpaceSoft, setNewSpaceSoft] = useState(80);
  const [newFilesHard, setNewFilesHard] = useState(100000);

  const clearSuccess = () => setTimeout(() => setSuccess(null), 3000);

  const loadRules = async () => {
    if (!volumeName) return;
    setLoading(true);
    setError(null);
    try {
      const response = await (client.queries as any).adminQuery({ action: "listQuotaRules", params: JSON.stringify({volumeName}) });
      const data = parseResponse<{ rules?: QuotaRule[]; error?: string }>(response);
      if (data) {
        if (data.error) setError(data.error);
        else setRules(data.rules || []);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load quota rules");
    } finally {
      setLoading(false);
    }
  };

  const loadReport = async () => {
    if (!volumeName) return;
    setLoading(true);
    setError(null);
    try {
      const response = await (client.queries as any).adminQuery({ action: "getQuotaReport", params: JSON.stringify({volumeName}) });
      const data = parseResponse<{ usage?: QuotaUsage[]; error?: string }>(response);
      if (data) {
        if (data.error) setError(data.error);
        else setUsage(data.usage || []);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load quota report");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!volumeName) return;
    if (activeTab === "rules") {
      loadRules();
    } else {
      loadReport();
    }
  }, [volumeName, activeTab]);

  const handleCreate = async () => {
    setError(null);
    try {
      const response = await (client.mutations as any).adminMutation({ action: "createQuotaRule", params: JSON.stringify({
        volumeName, type: newType, qtreeName: newType === "tree" ? newQtreeName : undefined,
        userName: newType === "user" ? newUserName : undefined,
        groupName: newType === "group" ? newGroupName : undefined,
        spaceHardLimitGiB: newSpaceHard, spaceSoftLimitGiB: newSpaceSoft, filesHardLimit: newFilesHard,
      }) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) {
          setSuccess(t("rmQuotaCreated"));
          setShowCreateForm(false);
          clearSuccess();
          loadRules();
        } else setError(data.error || "Create failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Create failed"); }
  };

  const handleDelete = async (ruleUuid: string) => {
    if (!window.confirm(t("rmDeleteConfirm"))) return;
    try {
      const response = await (client.mutations as any).adminMutation({ action: "deleteQuotaRule", params: JSON.stringify({ruleUuid}) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) { setSuccess(t("rmDeleted")); clearSuccess(); loadRules(); }
        else setError(data.error || "Delete failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Delete failed"); }
  };

  if (loading && !volumeName) return <p className="loading">{t("loading")}</p>;

  return (
    <div className="admin-panel">
      <div className="panel-header">
        <h3>{t("rmQuotas")}</h3>
        <div className="panel-actions">
          <VolumeSelector
            label={t("rmSelectVolume")}
            onSelect={(vol) => setVolumeName(vol.name)}
            autoSelectFirst
          />
          <button onClick={() => setActiveTab("rules")}
            className={activeTab === "rules" ? "btn-primary" : "btn-secondary"}>{t("rmQuotaRules")}</button>
          <button onClick={() => setActiveTab("report")}
            className={activeTab === "report" ? "btn-primary" : "btn-secondary"}>{t("rmQuotaReport")}</button>
          <button onClick={() => setShowCreateForm(!showCreateForm)} className="btn-primary">+ {t("rmCreateQuota")}</button>
          <button onClick={activeTab === "rules" ? loadRules : loadReport} className="refresh-btn">↻</button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}
      {success && <div className="success-message">{success}</div>}

      {showCreateForm && (
        <div className="create-form">
          <div className="form-row">
            <div className="form-group">
              <label>{t("rmQuotaType")}</label>
              <select value={newType} onChange={(e) => setNewType(e.target.value as "tree" | "user" | "group")}>
                <option value="tree">Tree</option>
                <option value="user">User</option>
                <option value="group">Group</option>
              </select>
            </div>
            {newType === "tree" && (
              <div className="form-group">
                <label>{t("rmQuotaTarget")}</label>
                <input type="text" value={newQtreeName} onChange={(e) => setNewQtreeName(e.target.value)} />
              </div>
            )}
            {newType === "user" && (
              <div className="form-group">
                <label>{t("rmQuotaTarget")}</label>
                <input type="text" value={newUserName} onChange={(e) => setNewUserName(e.target.value)} />
              </div>
            )}
            {newType === "group" && (
              <div className="form-group">
                <label>{t("rmQuotaTarget")}</label>
                <input type="text" value={newGroupName} onChange={(e) => setNewGroupName(e.target.value)} />
              </div>
            )}
            <div className="form-group">
              <label>{t("rmSpaceHardLimit")} (GiB)</label>
              <input type="number" value={newSpaceHard} onChange={(e) => setNewSpaceHard(parseInt(e.target.value))} min={1} />
            </div>
            <div className="form-group">
              <label>{t("rmSpaceSoftLimit")} (GiB)</label>
              <input type="number" value={newSpaceSoft} onChange={(e) => setNewSpaceSoft(parseInt(e.target.value))} min={1} />
            </div>
            <div className="form-group">
              <label>{t("rmFilesHardLimit")}</label>
              <input type="number" value={newFilesHard} onChange={(e) => setNewFilesHard(parseInt(e.target.value))} min={1} />
            </div>
          </div>
          <button onClick={handleCreate} className="btn-primary">{t("rmCreate")}</button>
          <button onClick={() => setShowCreateForm(false)} className="btn-secondary">{t("cancel")}</button>
        </div>
      )}

      {loading ? <p className="loading">{t("loading")}</p> : activeTab === "rules" ? (
        <table className="admin-table">
          <thead>
            <tr><th>{t("rmQuotaType")}</th><th>{t("rmQuotaTarget")}</th><th>{t("rmSpaceHardLimit")}</th><th>{t("rmSpaceSoftLimit")}</th><th>{t("rmFilesHardLimit")}</th><th>{t("rmActions")}</th></tr>
          </thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.uuid}>
                <td>{r.type}</td>
                <td>{r.qtreeName || r.userName || r.groupName || "-"}</td>
                <td>{r.spaceHardLimitGiB} GiB</td>
                <td>{r.spaceSoftLimitGiB} GiB</td>
                <td>{r.filesHardLimit}</td>
                <td><button onClick={() => handleDelete(r.uuid)} className="btn-sm btn-danger">✕</button></td>
              </tr>
            ))}
            {rules.length === 0 && <tr><td colSpan={6} className="empty-state">{t("rmNoQuotaRules")}</td></tr>}
          </tbody>
        </table>
      ) : (
        <div>
          {usage.length === 0 ? <p className="empty-state">{t("rmNoQuotaData")}</p> : usage.map((u, i) => (
            <div key={i} style={{ marginBottom: "1rem" }}>
              <strong>{u.target}</strong> ({u.type}) — {t("rmQuotaUsage")}
              <div className="capacity-bar">
                <div className="capacity-fill" style={{ width: `${Math.min((u.spaceUsedGiB / u.spaceHardLimitGiB) * 100, 100)}%`,
                  backgroundColor: (u.spaceUsedGiB / u.spaceHardLimitGiB) > 0.9 ? "#ef4444" : "#22c55e" }} />
              </div>
              <span>{u.spaceUsedGiB} / {u.spaceHardLimitGiB} GiB</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
