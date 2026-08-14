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

  // Create form state. No volume of its own: the qtree is created in the volume
  // the list is filtered to, so there is nothing here for the two to disagree
  // about. See the form markup below for what the second selector cost.
  const [newName, setNewName] = useState("");
  const [newSecurityStyle, setNewSecurityStyle] = useState("unix");
  const [newExportPolicy, setNewExportPolicy] = useState("default");

  const clearSuccess = () => setTimeout(() => setSuccess(null), 3000);

  // Keyed on the selected volume, so picking a different volume switches lists
  // without a manual reload. Disabled until a volume is chosen.
  //
  // `isFetching`, not `isPending`: a disabled query stays `status: "pending"`
  // forever because it has no data, so `isPending` means "nothing loaded yet",
  // not "a request is in flight". Reading it as loading rendered the spinner
  // before any volume was chosen — and the only control that chooses one is
  // below, so the spinner hid the way out of itself. `isFetching` is false
  // while the query is disabled, which is what the other panels use.
  const {
    data: qtrees = [],
    isFetching: loading,
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
    if (!filterVolume || !newName) { setError("Volume name and qtree name are required"); return; }
    setError(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "createQtree",
        params: {
          volumeName: filterVolume, name: newName,
          securityStyle: newSecurityStyle, exportPolicy: newExportPolicy,
        },
      });
      if (data) {
        if (data.success) {
          setSuccess(t("rmQtreeCreated"));
          setShowCreateForm(false);
          setNewName(""); setNewExportPolicy("default");
          clearSuccess();
          // Unconditional: the qtree went into the volume the list is showing, so
          // there is always something new to display. This used to be guarded by
          // a comparison against the form's own volume, and when they differed
          // nothing happened -- the success message appeared above a list that
          // could not contain the new qtree.
          loadQtrees();
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
            excludeFlexCache
          />
          {/* Disabled until a volume is chosen, because the volume the qtree goes
              into is now the one selected above. Opening the form without one
              would offer a field-less form that could only fail on submit. */}
          <button onClick={() => setShowCreateForm(!showCreateForm)} className="btn-primary"
            disabled={!filterVolume}>
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
            {/* The target volume, shown rather than chosen.
                A second VolumeSelector stood here. It carried its own selection,
                independent of the one filtering the list, so creating a qtree
                could land it in a volume the list was not showing: the success
                message appeared and the table below it stayed unchanged, which
                reads as a create that silently failed. Every sibling panel
                (quota, snaplock, snapshot) already creates against the volume
                selected in its header; this makes the qtree panel behave the
                same way. To create somewhere else, switch the volume above. */}
            <div className="form-group">
              <label>{t("rmQtreeVolume")}</label>
              <p className="form-static-value">{filterVolume}</p>
            </div>
            <div className="form-group">
              <label>{t("rmQtreeName")}</label>
              {/* A qtree name is a case-sensitive ONTAP identifier, and iOS Safari
                  defaults text inputs to autocapitalize="sentences" -- so a name
                  typed on a phone arrives with its first letter changed, and the
                  qtree is created under a name the user did not type. autoCorrect
                  and spellCheck are off for the same reason: an identifier is not
                  prose. */}
              <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)}
                placeholder="qtree_name"
                autoCapitalize="none" autoCorrect="off" spellCheck={false} />
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
            {qtrees.map((q) => {
              // ONTAP reports the volume's own root as a qtree with an empty name, so
              // every volume has one and it is always the first row. It is not
              // something anyone created and ONTAP will not delete it, so it is named
              // here and carries no delete button -- a blank row with a ✕ beside it
              // read as a qtree whose name had failed to load.
              const isVolumeRoot = !q.name;
              return (
                <tr key={q.id}>
                  <td>
                    {isVolumeRoot ? (
                      <span className="row-derived">{t("rmQtreeVolumeRoot")}</span>
                    ) : (
                      q.name
                    )}
                  </td>
                  <td>{q.volumeName}</td>
                  <td>{q.securityStyle}</td>
                  <td>{q.exportPolicy}</td>
                  <td className="action-cell">
                    {!isVolumeRoot && (
                      <button onClick={() => handleDelete(q.volumeName, q.id, q.name)}
                        className="btn-sm btn-danger">✕</button>
                    )}
                  </td>
                </tr>
              );
            })}
            {/* Before a volume is chosen there is nothing to have found, so the
                prompt is shown rather than "none found". */}
            {qtrees.length === 0 && (
              <tr>
                <td colSpan={5} className="empty-state">
                  {filterVolume ? t("rmNoQtrees") : t("rmSelectVolumePlaceholder")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
