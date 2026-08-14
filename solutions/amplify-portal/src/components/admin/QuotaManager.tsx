import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage, unwrap } from "../../lib/portalQuery";
import { adminMutate, dispatch } from "../../lib/dispatch";
import { VolumeSelector } from "./VolumeSelector";

/** A rule as `listQuotaRules` returns it.
 *
 * Limits are bytes, and the user target is a list, because that is what ONTAP
 * reports and the handler passes through. The previous declaration here used
 * `userName` and `...GiB` names the handler never sent, so every limit cell
 * rendered "undefined GiB" once a rule existed.
 */
interface QuotaRule {
  uuid: string;
  type: string;
  volumeName?: string;
  qtreeName?: string;
  users?: string[];
  groupName?: string;
  spaceHardLimit?: number | null;
  spaceSoftLimit?: number | null;
  filesHardLimit?: number | null;
}

/** An entry as `getQuotaReport` returns it, under `entries` rather than `usage`. */
interface QuotaUsage {
  type: string;
  volumeName?: string;
  qtreeName?: string;
  users?: string[];
  groupName?: string;
  spaceUsed: number;
  spaceHardLimit: number;
  spaceUsedPercent: number;
  filesUsed: number;
  filesHardLimit: number;
}

const BYTES_PER_GIB = 1024 ** 3;

/** Bytes to GiB for display. ONTAP omits a limit rather than sending 0. */
function limitGiB(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  return `${(bytes / BYTES_PER_GIB).toFixed(1)} GiB`;
}

/** The target column: whichever of qtree / user / group this rule is for. */
function ruleTarget(r: QuotaRule | QuotaUsage): string {
  return r.qtreeName || r.users?.join(", ") || r.groupName || "-";
}

export function QuotaManager() {
  const { t } = useTranslation();
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
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

  // Rules and the usage report are separate queries so each tab keeps its own
  // cache entry, both keyed on the selected volume.
  const rulesQuery = useQuery({
    queryKey: ["admin", "listQuotaRules", volumeName],
    enabled: !!volumeName && activeTab === "rules",
    queryFn: () =>
      unwrap<{ rules?: QuotaRule[] }>(
        dispatch("adminQuery", { action: "listQuotaRules", params: { volumeName } }),
      ).then((d) => d?.rules ?? []),
  });

  const reportQuery = useQuery({
    queryKey: ["admin", "getQuotaReport", volumeName],
    enabled: !!volumeName && activeTab === "report",
    queryFn: () =>
      unwrap<{ entries?: QuotaUsage[] }>(
        dispatch("adminQuery", { action: "getQuotaReport", params: { volumeName } }),
      ).then((d) => d?.entries ?? []),
  });

  const rules = rulesQuery.data ?? [];
  const usage = reportQuery.data ?? [];
  const loading = rulesQuery.isFetching || reportQuery.isFetching;

  // Mutation handlers report through their own state, so a failed action is
  // never mistaken for a failed load.
  const loadRules = () => void rulesQuery.refetch();
  const loadReport = () => void reportQuery.refetch();
  const error =
    actionError ??
    errorMessage(rulesQuery.error ?? reportQuery.error, "Failed to load quotas");

  const handleCreate = async () => {
    setError(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "createQuotaRule",
        params: {
          volumeName, type: newType, qtreeName: newType === "tree" ? newQtreeName : undefined,
          userName: newType === "user" ? newUserName : undefined,
          groupName: newType === "group" ? newGroupName : undefined,
          spaceHardLimitGiB: newSpaceHard, spaceSoftLimitGiB: newSpaceSoft, filesHardLimit: newFilesHard,
        },
      });
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
      const data = await adminMutate<{ success?: boolean }>({
        action: "deleteQuotaRule",
        params: { ruleUuid },
      });
      if (data) {
        if (data.success) { setSuccess(t("rmDeleted")); clearSuccess(); loadRules(); }
        else setError(data.error || "Delete failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Delete failed"); }
  };

  // No early return on `loading && !volumeName`: this panel's only volume
  // control is inside the markup below, so hiding the markup while waiting for a
  // volume would remove the way to supply one. The branch was unreachable here
  // because `isFetching` is false while a query is disabled, but the same line
  // read against `isPending` deadlocked the qtree panel.
  return (
    <div className="admin-panel">
      <div className="panel-header">
        <h3>{t("rmQuotas")}</h3>
        <div className="panel-actions">
          <VolumeSelector
            label={t("rmSelectVolume")}
            onSelect={(vol) => setVolumeName(vol.name)}
            autoSelectFirst
            excludeFlexCache
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
                <td>{ruleTarget(r)}</td>
                <td>{limitGiB(r.spaceHardLimit)}</td>
                <td>{limitGiB(r.spaceSoftLimit)}</td>
                <td>{r.filesHardLimit ?? "—"}</td>
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
              <strong>{ruleTarget(u)}</strong> ({u.type}) — {t("rmQuotaUsage")}
              <div className="capacity-bar">
                <div className="capacity-fill" style={{ width: `${Math.min(u.spaceUsedPercent, 100)}%`,
                  backgroundColor: u.spaceUsedPercent > 90 ? "var(--color-error)" : "var(--color-success)" }} />
              </div>
              <span>{limitGiB(u.spaceUsed)} / {limitGiB(u.spaceHardLimit)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
