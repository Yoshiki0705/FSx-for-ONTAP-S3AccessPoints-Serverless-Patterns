import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage, unwrap } from "../../lib/portalQuery";
import { adminMutate, dispatch } from "../../lib/dispatch";
import type { QtreeId } from "../../lib/dispatchActions";
import { VolumeSelector } from "./VolumeSelector";

interface Qtree {
  /** ONTAP's qtree identifier, branded where it arrives. Not the qtree name. */
  id: QtreeId;
  name: string;
  volumeName: string;
  securityStyle: string;
  exportPolicy: string;
}

export function QtreeManager() {
  const { t } = useTranslation();
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
  const [success, setSuccess] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [filterVolume, setFilterVolume] = useState("");

  // Create form state
  const [newVolumeName, setNewVolumeName] = useState("");
  const [newName, setNewName] = useState("");
  const [newSecurityStyle, setNewSecurityStyle] = useState("unix");
  const [newExportPolicy, setNewExportPolicy] = useState("default");

  const clearSuccess = () => setTimeout(() => setSuccess(null), 3000);

  // Keyed on the selected volume, so picking a different volume switches lists
  // without a manual reload. Disabled until a volume is chosen.
  const {
    data: qtrees = [],
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "listQtrees", filterVolume],
    enabled: !!filterVolume,
    queryFn: () =>
      unwrap<{ qtrees?: Qtree[] }>(
        dispatch("adminQuery", {
          action: "listQtrees",
          params: { volumeName: filterVolume },
        }),
      ).then((d) => d?.qtrees ?? []),
  });

  // Mutation handlers report through their own state, so a failed action is
  // never mistaken for a failed load.
  const loadQtrees = () => void refetch();
  const error = actionError ?? errorMessage(queryError, "Failed to load qtrees");

  const handleCreate = async () => {
    if (!newVolumeName || !newName) { setError("Volume name and qtree name are required"); return; }
    setError(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "createQtree",
        params: {
          volumeName: newVolumeName, name: newName,
          securityStyle: newSecurityStyle, exportPolicy: newExportPolicy,
        },
      });
      if (data) {
        if (data.success) {
          setSuccess(t("rmQtreeCreated"));
          setShowCreateForm(false);
          setNewName(""); setNewExportPolicy("default");
          clearSuccess();
          if (newVolumeName === filterVolume) loadQtrees();
        } else setError(data.error || "Create failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Create failed"); }
  };

  const handleDelete = async (volumeName: string, qtreeId: QtreeId, name: string) => {
    if (!window.confirm(t("rmDeleteConfirm").replace("{name}", name))) return;
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "deleteQtree",
        params: { volumeName, qtreeId, confirm: true },
      });
      if (data) {
        if (data.success) { setSuccess(t("rmDeleted").replace("{name}", name)); clearSuccess(); loadQtrees(); }
        else setError(data.error || "Delete failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Delete failed"); }
  };

  if (loading && !filterVolume) return <p className="loading">{t("loading")}</p>;

  return (
    <div className="admin-panel">
      <div className="panel-header">
        <h3>{t("rmQtrees")}</h3>
        <div className="panel-actions">
          <VolumeSelector
            label=""
            onSelect={(vol) => setFilterVolume(vol.name)}
            autoSelectFirst
            enableSearch
          />
          <button onClick={() => setShowCreateForm(!showCreateForm)} className="btn-primary">
            + {t("rmCreateQtree")}
          </button>
          <button onClick={loadQtrees} className="refresh-btn">↻</button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}
      {success && <div className="success-message">{success}</div>}

      {showCreateForm && (
        <div className="create-form">
          <div className="form-row">
            <div className="form-group">
              <label>{t("rmQtreeVolume")}</label>
              <VolumeSelector
                onSelect={(vol) => setNewVolumeName(vol.name)}
                enableSearch
              />
            </div>
            <div className="form-group">
              <label>{t("rmQtreeName")}</label>
              <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)}
                placeholder="qtree_name" />
            </div>
            <div className="form-group">
              <label>{t("rmSecurityStyle")}</label>
              <select value={newSecurityStyle} onChange={(e) => setNewSecurityStyle(e.target.value)}>
                <option value="unix">UNIX</option>
                <option value="ntfs">NTFS</option>
                <option value="mixed">Mixed</option>
              </select>
            </div>
            <div className="form-group">
              <label>Export Policy</label>
              <input type="text" value={newExportPolicy} onChange={(e) => setNewExportPolicy(e.target.value)}
                placeholder="default" />
            </div>
          </div>
          <button onClick={handleCreate} className="btn-primary">{t("rmCreate")}</button>
          <button onClick={() => setShowCreateForm(false)} className="btn-secondary">{t("cancel")}</button>
        </div>
      )}

      {loading ? <p className="loading">{t("loading")}</p> : (
        <table className="admin-table">
          <thead>
            <tr>
              <th>{t("rmQtreeName")}</th>
              <th>{t("rmQtreeVolume")}</th>
              <th>{t("rmSecurityStyle")}</th>
              <th>Export Policy</th>
              <th>{t("rmActions")}</th>
            </tr>
          </thead>
          <tbody>
            {qtrees.map((q) => (
              <tr key={q.id}>
                <td>{q.name}</td>
                <td>{q.volumeName}</td>
                <td>{q.securityStyle}</td>
                <td>{q.exportPolicy}</td>
                <td className="action-cell">
                  <button onClick={() => handleDelete(q.volumeName, q.id, q.name)}
                    className="btn-sm btn-danger">✕</button>
                </td>
              </tr>
            ))}
            {qtrees.length === 0 && (
              <tr><td colSpan={5} className="empty-state">{t("rmNoQtrees")}</td></tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
