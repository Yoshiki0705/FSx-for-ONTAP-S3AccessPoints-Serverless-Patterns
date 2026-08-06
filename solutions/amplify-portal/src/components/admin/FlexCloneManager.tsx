import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { errorMessage } from "../../lib/portalQuery";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";
import { parseResponse } from "../../utils/parseResponse";

const client = generateClient<Schema>();

interface FlexClone {
  name: string;
  uuid: string;
  sizeGiB: number;
  state: string;
  parentVolume: string;
  parentSnapshot: string;
  splitInitiated: boolean;
  splitCompletePercent: number;
  usedGiB: number;
}

export function FlexCloneManager() {
  const { t } = useTranslation();
  // Errors raised by the create/split handlers, kept separate from the query's own
  // error so a failed action does not read as a failed load, and vice versa.
  const [actionError, setActionError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const [cloneName, setCloneName] = useState("");
  const [parentVolume, setParentVolume] = useState("");
  const [parentSnapshot, setParentSnapshot] = useState("");

  const clearSuccess = () => setTimeout(() => setSuccess(null), 3000);

  // Deliberately not using `unwrap` here. This action tolerates two payload errors
  // — "Unknown action" and "not configured" — and shows an empty list instead,
  // because FlexClone is optional and a cluster without it should render an empty
  // panel rather than an error. `unwrap` promotes every payload error to a
  // rejection, which would turn that supported configuration into a failure.
  const {
    data: clones = [],
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "listFlexClones"],
    queryFn: async () => {
      const resp = await client.queries.adminQuery({ action: "listFlexClones", params: JSON.stringify({}) });
      const data = parseResponse<{ clones?: FlexClone[]; error?: string }>(resp);
      if (data?.error && !data.error.includes("Unknown action") && !data.error.includes("not configured")) {
        throw new Error(data.error);
      }
      return data?.clones ?? [];
    },
  });

  const loadClones = () => void refetch();
  const setError = setActionError;
  const error = actionError ?? errorMessage(queryError, "Load failed");

  const handleCreate = async () => {
    if (!cloneName || !parentVolume) { setError(t("fcCloneNameRequired")); return; }
    setError(null);
    try {
      const resp = await client.mutations.adminMutation({
        action: "createFlexClone",
        params: JSON.stringify({ cloneName, parentVolume, parentSnapshot }),
      });
      const data = parseResponse<{ success?: boolean; error?: string }>(resp);
      if (data?.success) {
        setSuccess(t("fcCloneCreated")); setShowCreate(false);
        setCloneName(""); setParentVolume(""); setParentSnapshot("");
        clearSuccess(); loadClones();
      } else setError(data?.error || "Create failed");
    } catch (e) { setError(e instanceof Error ? e.message : "Create failed"); }
  };

  const handleSplit = async (clone: FlexClone) => {
    if (!window.confirm(t("fcSplitConfirm").replace("{name}", clone.name))) return;
    try {
      const resp = await client.mutations.adminMutation({
        action: "splitFlexClone",
        params: JSON.stringify({ volumeUuid: clone.uuid, volumeName: clone.name }),
      });
      const data = parseResponse<{ success?: boolean; error?: string }>(resp);
      if (data?.success) { setSuccess(t("fcSplitInitiated")); clearSuccess(); loadClones(); }
      else setError(data?.error || "Split failed");
    } catch (e) { setError(e instanceof Error ? e.message : "Split failed"); }
  };

  return (
    <div className="flexclone-manager">
      {error && <div className="rm-error">⚠️ {error}</div>}
      {success && <div className="rm-success">✅ {success}</div>}

      <div className="lu-toolbar">
        <span className="lu-count">{clones.length} FlexClones</span>
        <button className="rm-btn-primary" onClick={() => setShowCreate(true)}>+ {t("fcCreateClone")}</button>
      </div>

      {showCreate && (
        <div className="rm-create-form">
          <h4>{t("fcCreateClone")}</h4>
          <div className="rm-form-row">
            <label>{t("fcCloneName")}</label>
            <input type="text" value={cloneName} onChange={e => setCloneName(e.target.value)} placeholder="clone_dev_01" />
          </div>
          <div className="rm-form-row">
            <label>{t("fcParentVolume")}</label>
            <input type="text" value={parentVolume} onChange={e => setParentVolume(e.target.value)} placeholder="vol_production" />
          </div>
          <div className="rm-form-row">
            <label>{t("fcParentSnapshot")}</label>
            <input type="text" value={parentSnapshot} onChange={e => setParentSnapshot(e.target.value)} placeholder={t("fcSnapshotOptional")} />
          </div>
          <div className="rm-form-actions">
            <button className="rm-btn-primary" onClick={handleCreate}>{t("rmCreate")}</button>
            <button className="rm-btn-secondary" onClick={() => setShowCreate(false)}>{t("cancel")}</button>
          </div>
          <p className="rm-hint">{t("fcCreateHint")}</p>
        </div>
      )}

      {loading ? <div className="rm-loading">{t("ontapConnecting")}</div> : clones.length === 0 ? (
        <p className="rm-empty">{t("fcNoClones")}</p>
      ) : (
        <table className="rm-table">
          <thead><tr>
            <th>{t("fcCloneName")}</th><th>{t("fcParentVolume")}</th><th>{t("fcParentSnapshot")}</th>
            <th>{t("rmVolumeSize")}</th><th>{t("rmState")}</th><th>{t("rmActions")}</th>
          </tr></thead>
          <tbody>
            {clones.map(c => (
              <tr key={c.uuid}>
                <td className="lu-username">{c.name}</td>
                <td>{c.parentVolume}</td>
                <td>{c.parentSnapshot || "—"}</td>
                <td>{c.sizeGiB} GiB</td>
                <td>
                  {c.splitInitiated ? (
                    <span className="lu-badge active">{t("fcSplitting")} {c.splitCompletePercent}%</span>
                  ) : (
                    <span className="lu-badge">{c.state}</span>
                  )}
                </td>
                <td>
                  {!c.splitInitiated && (
                    <button className="rm-btn-sm" onClick={() => handleSplit(c)}>{t("fcSplit")}</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
