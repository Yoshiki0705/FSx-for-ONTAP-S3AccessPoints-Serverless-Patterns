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

interface CifsShare {
  name: string;
  path: string;
  comment: string;
  encryption: boolean;
  continuouslyAvailable: boolean;
}

export function CifsShareManager() {
  const { t } = useTranslation();
  const [shares, setShares] = useState<CifsShare[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);

  // Create form state
  const [newName, setNewName] = useState("");
  const [newPath, setNewPath] = useState("");
  const [newComment, setNewComment] = useState("");

  const clearSuccess = () => setTimeout(() => setSuccess(null), 3000);

  const loadShares = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await (client.queries as any).adminQuery({ action: "listCifsShares", params: JSON.stringify({}) });
      const data = parseResponse<{ shares?: CifsShare[]; error?: string }>(response);
      if (data) {
        if (data.error) setError(data.error);
        else setShares(data.shares || []);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load CIFS shares");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadShares(); }, []);

  const handleCreate = async () => {
    if (!newName || !newPath) { setError("Name and path are required"); return; }
    setError(null);
    try {
      const response = await (client.mutations as any).adminMutation({ action: "createCifsShare", params: JSON.stringify({
        name: newName, path: newPath, comment: newComment,
      }) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) {
          setSuccess(t("rmShareCreated"));
          setShowCreateForm(false);
          setNewName(""); setNewPath(""); setNewComment("");
          clearSuccess();
          loadShares();
        } else setError(data.error || "Create failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Create failed"); }
  };

  const handleDelete = async (name: string) => {
    if (!window.confirm(t("rmShareDeleteConfirm").replace("{name}", name))) return;
    try {
      const response = await (client.mutations as any).adminMutation({ action: "deleteCifsShare", params: JSON.stringify({name, confirm: true}) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) { setSuccess(t("rmShareDeleted").replace("{name}", name)); clearSuccess(); loadShares(); }
        else setError(data.error || "Delete failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Delete failed"); }
  };

  const handleToggleEncryption = async (name: string, enable: boolean) => {
    setError(null);
    try {
      const response = await (client.mutations as any).adminMutation({
        action: "updateCifsShare",
        params: JSON.stringify({ name, encryption: enable }),
      });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) {
          setSuccess(enable ? t("rmEncryptionEnabled") : t("rmEncryptionDisabled"));
          clearSuccess();
          loadShares();
        } else setError(data.error || "Update failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Update failed"); }
  };

  if (loading) return <p className="loading">{t("loading")}</p>;

  return (
    <div className="admin-panel">
      <div className="panel-header">
        <h3>{t("rmCifsShares")}</h3>
        <div className="panel-actions">
          <button onClick={() => setShowCreateForm(!showCreateForm)} className="btn-primary">
            + {t("rmCreateShare")}
          </button>
          <button onClick={loadShares} className="refresh-btn">↻</button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}
      {success && <div className="success-message">{success}</div>}

      {showCreateForm && (
        <div className="create-form">
          <div className="form-row">
            <div className="form-group">
              <label>{t("rmShareName")}</label>
              <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)}
                placeholder="share_name" />
            </div>
            <div className="form-group">
              <label>{t("rmSharePath")}</label>
              <input type="text" value={newPath} onChange={(e) => setNewPath(e.target.value)}
                placeholder="/vol/data" />
            </div>
            <div className="form-group">
              <label>{t("rmShareComment")}</label>
              <input type="text" value={newComment} onChange={(e) => setNewComment(e.target.value)}
                placeholder="Optional description" />
            </div>
          </div>
          <button onClick={handleCreate} className="btn-primary">{t("rmCreate")}</button>
          <button onClick={() => setShowCreateForm(false)} className="btn-secondary">{t("cancel")}</button>
        </div>
      )}

      {/* Info: encryption context */}
      <div className="info-message" style={{ marginBottom: "1rem" }}>
        🔒 {t("rmSmbEncryptionNote")}
      </div>

      {/* Info: CA share explanation */}
      <details style={{ marginBottom: "1rem", fontSize: "0.85rem" }}>
        <summary style={{ cursor: "pointer", fontWeight: 500 }}>
          ℹ️ {t("rmCaShareExplanationTitle")}
        </summary>
        <div style={{ marginTop: "0.5rem", padding: "0.5rem", background: "#f8f9fa", borderRadius: "4px" }}>
          <p style={{ margin: "0 0 0.5rem" }}>{t("rmCaShareExplanationDesc")}</p>
          <a href="https://docs.netapp.com/us-en/ontap/smb-hyper-v-sql/configure-solutions-concept.html"
            target="_blank" rel="noopener noreferrer" style={{ fontSize: "0.8rem" }}>
            📖 ONTAP Docs: Hyper-V and SQL Server over SMB solutions
          </a>
        </div>
      </details>

      <table className="admin-table">
        <thead>
          <tr>
            <th>{t("rmShareName")}</th>
            <th>{t("rmSharePath")}</th>
            <th>{t("rmShareComment")}</th>
            <th title={t("rmSmbEncryptionColTooltip")}>{t("rmSmbEncryptionCol")}</th>
            <th title={t("rmCaShareColTooltip")}>{t("rmCaShareCol")}</th>
            <th>{t("rmActions")}</th>
          </tr>
        </thead>
        <tbody>
          {shares.map((s) => (
            <tr key={s.name}>
              <td>{s.name}</td>
              <td><code>{s.path}</code></td>
              <td>{s.comment || "-"}</td>
              <td>
                {s.encryption ? (
                  <span className="state-badge state-online">✅ {t("rmSmbEncryptionOn")}</span>
                ) : (
                  <span className="badge">— {t("rmSmbEncryptionOff")}</span>
                )}
                <button
                  onClick={() => handleToggleEncryption(s.name, !s.encryption)}
                  className="btn-sm"
                  style={{ marginLeft: "0.5rem" }}
                  title={s.encryption ? t("rmEncryptionDisable") : `${t("rmEncryptionEnable")}\n${t("rmEncryptionClientWarning")}`}
                >
                  {s.encryption ? "OFF" : "ON"}
                </button>
              </td>
              <td>
                {s.continuouslyAvailable ? (
                  <span className="state-badge state-online">{t("rmCaEnabled")}</span>
                ) : (
                  <span className="badge">— {t("rmCaNotNeeded")}</span>
                )}
              </td>
              <td className="action-cell">
                <button onClick={() => handleDelete(s.name)} className="btn-sm btn-danger">
                  {t("rmShareDeleteBtn")}
                </button>
              </td>
            </tr>
          ))}
          {shares.length === 0 && (
            <tr><td colSpan={6} className="empty-state">{t("rmNoShares")}</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
