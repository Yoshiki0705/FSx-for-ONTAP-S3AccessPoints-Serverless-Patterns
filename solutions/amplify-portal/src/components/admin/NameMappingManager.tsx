import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage } from "../../lib/portalQuery";
import { adminMutate, adminQuery } from "../../lib/dispatch";

interface NameMapping {
  direction: string;
  index: number;
  pattern: string;
  replacement: string;
}

export function NameMappingManager() {
  const { t } = useTranslation();
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
  const [success, setSuccess] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const [newDirection, setNewDirection] = useState("win_unix");
  const [newIndex, setNewIndex] = useState(1);
  const [newPattern, setNewPattern] = useState("");
  const [newReplacement, setNewReplacement] = useState("");
  // The rule being edited, identified by direction and index -- which together are
  // its identity, and are the two things this form does not change.
  const [editing, setEditing] = useState<NameMapping | null>(null);
  const [editPattern, setEditPattern] = useState("");
  const [editReplacement, setEditReplacement] = useState("");

  const clearSuccess = () => setTimeout(() => setSuccess(null), 3000);

  const {
    data: mappings = [],
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "listNameMappings"],
    queryFn: async () => {
      const data = await adminQuery<{ mappings?: NameMapping[] }>({ action: "listNameMappings" });
      // A dispatcher that has not been wired yet is an empty list, not a failure.
      if (
        data?.error &&
        !data.error.includes("Unknown action") &&
        !data.error.includes("not configured")
      ) {
        throw new Error(data.error);
      }
      return data?.mappings ?? [];
    },
  });

  // Mutation handlers report through their own state, so a failed action is
  // never mistaken for a failed load.
  const loadMappings = () => void refetch();
  const error = actionError ?? errorMessage(queryError, "Failed to load mappings");


  const handleCreate = async () => {
    if (!newPattern || !newReplacement) {
      setError(t("nmPatternRequired")); return;
    }
    setError(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "createNameMapping",
        params: {
          direction: newDirection,
          index: newIndex,
          pattern: newPattern,
          replacement: newReplacement,
        },
      });
      if (data?.success) {
        setSuccess(t("nmCreated")); setShowCreate(false);
        setNewPattern(""); setNewReplacement("");
        clearSuccess(); loadMappings();
      } else setError(data?.error || "Create failed");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    }
  };

  /**
   * Save an edited pattern and replacement.
   *
   * Getting a mapping's regular expression right is iterative, and until now each
   * correction was a delete and a create. Between those two calls the rule did not
   * exist, so everyone it covered fell through to whatever the next rule said.
   */
  const handleSaveEdit = async () => {
    if (!editing) return;
    if (!editPattern.trim()) { setError(t("nmPatternRequired")); return; }
    setError(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "updateNameMapping",
        params: {
          direction: editing.direction,
          index: editing.index,
          pattern: editPattern.trim(),
          replacement: editReplacement.trim(),
        },
      });
      if (data?.success) {
        setSuccess(t("nmUpdated"));
        setEditing(null);
        clearSuccess();
        loadMappings();
      } else setError(data?.error || "Update failed");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    }
  };

  const handleDelete = async (m: NameMapping) => {
    if (!window.confirm(
      t("nmDeleteConfirm")
        .replace("{dir}", m.direction)
        .replace("{idx}", String(m.index))
    )) return;
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "deleteNameMapping",
        params: { direction: m.direction, index: m.index },
      });
      if (data?.success) {
        setSuccess(t("nmDeleted")); clearSuccess(); loadMappings();
      } else setError(data?.error || "Delete failed");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  const directionLabel = (d: string) => {
    switch (d) {
      case "win_unix": return "Windows → UNIX";
      case "unix_win": return "UNIX → Windows";
      case "s3_unix": return "S3 → UNIX";
      case "s3_win": return "S3 → Windows";
      default: return d;
    }
  };

  return (
    <div className="name-mapping-manager">
      {error && <div className="rm-error">⚠️ {error}</div>}
      {success && <div className="rm-success">✅ {success}</div>}

      <div className="lu-toolbar">
        <span className="lu-count">
          {mappings.length} {t("nmMappings")}
        </span>
        <button
          className="rm-btn-primary"
          onClick={() => setShowCreate(true)}
        >
          + {t("nmCreate")}
        </button>
      </div>

      {showCreate && (
        <div className="rm-create-form">
          <h4>{t("nmCreate")}</h4>
          <div className="rm-form-row">
            <label>{t("nmDirection")}</label>
            <select value={newDirection}
              onChange={e => setNewDirection(e.target.value)}>
              <option value="win_unix">Windows → UNIX</option>
              <option value="unix_win">UNIX → Windows</option>
              <option value="s3_unix">S3 → UNIX</option>
              <option value="s3_win">S3 → Windows</option>
            </select>
          </div>
          <div className="rm-form-row">
            <label>{t("nmIndex")}</label>
            <input type="number" min={1} max={100}
              value={newIndex}
              onChange={e => setNewIndex(Number(e.target.value))} />
          </div>
          <div className="rm-form-row">
            <label>{t("nmPattern")}</label>
            <input type="text" value={newPattern}
              onChange={e => setNewPattern(e.target.value)}
              placeholder="DOMAIN\\(.+)" />
          </div>
          <div className="rm-form-row">
            <label>{t("nmReplacement")}</label>
            <input type="text" value={newReplacement}
              onChange={e => setNewReplacement(e.target.value)}
              placeholder='\1' />
          </div>
          <div className="rm-form-actions">
            <button className="rm-btn-primary"
              onClick={handleCreate}>{t("rmCreate")}</button>
            <button className="rm-btn-secondary"
              onClick={() => setShowCreate(false)}>
              {t("cancel")}
            </button>
          </div>
          <p className="rm-hint">{t("nmHint")}</p>
        </div>
      )}

      {loading ? (
        <div className="rm-loading">{t("ontapConnecting")}</div>
      ) : mappings.length === 0 ? (
        <p className="rm-empty">{t("nmNoMappings")}</p>
      ) : (
        <>
        <p className="rm-hint">{t("nmEditHint")}</p>
        <table className="rm-table">
          <thead>
            <tr>
              <th>#</th>
              <th>{t("nmDirection")}</th>
              <th>{t("nmPattern")}</th>
              <th>{t("nmReplacement")}</th>
              <th>{t("rmActions")}</th>
            </tr>
          </thead>
          <tbody>
            {mappings.map(m => (
              <tr key={`${m.direction}-${m.index}`}>
                <td>{m.index}</td>
                <td>{directionLabel(m.direction)}</td>
                {editing?.direction === m.direction && editing?.index === m.index ? (
                  <>
                    <td>
                      <input
                        type="text"
                        value={editPattern}
                        onChange={e => setEditPattern(e.target.value)}
                        aria-label={t("nmPattern")}
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        value={editReplacement}
                        onChange={e => setEditReplacement(e.target.value)}
                        aria-label={t("nmReplacement")}
                      />
                    </td>
                    <td>
                      <span className="peer-accept-row">
                        <button className="rm-btn-primary" onClick={() => void handleSaveEdit()}>
                          {t("rmApply")}
                        </button>
                        <button className="rm-btn-sm" onClick={() => setEditing(null)}>
                          {t("cancel")}
                        </button>
                      </span>
                    </td>
                  </>
                ) : (
                  <>
                    <td className="lu-username">{m.pattern}</td>
                    <td>{m.replacement || '" "  (deny)'}</td>
                    <td>
                      <span className="peer-accept-row">
                        {/* s3_unix entries belong to FSx for ONTAP, which creates and
                            removes them with the S3 Access Point. */}
                        {m.direction !== "s3_unix" && (
                          <button
                            className="rm-btn-sm"
                            onClick={() => {
                              setEditing(m);
                              setEditPattern(m.pattern);
                              setEditReplacement(m.replacement);
                            }}
                          >
                            {t("nmEdit")}
                          </button>
                        )}
                        <button className="rm-btn-danger-sm" onClick={() => handleDelete(m)}>
                          {t("nmDelete")}
                        </button>
                      </span>
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        </>
      )}
    </div>
  );
}
