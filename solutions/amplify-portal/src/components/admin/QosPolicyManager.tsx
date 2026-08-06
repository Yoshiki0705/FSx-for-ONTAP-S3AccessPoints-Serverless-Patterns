import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";
import { errorMessage, unwrap } from "../../lib/portalQuery";
import { parseResponse } from "../../utils/parseResponse";

const client = generateClient<Schema>();

// Parse the JSON string response from generic dispatch endpoints

interface QosPolicy { name: string; uuid: string; type: string; maxThroughputIops?: number; maxThroughputMbps?: number; expectedIops?: number; peakIops?: number; }

/**
 * QoS Policy Manager — Create, view, delete QoS policies and assign to volumes.
 * System Manager-style: policy list + create form + assign action.
 */
export function QosPolicyManager() {
  const { t } = useTranslation();
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
  const [result, setResult] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  // Create form
  const [newName, setNewName] = useState("");
  const [policyType, setPolicyType] = useState<"fixed" | "adaptive">("fixed");
  const [maxIops, setMaxIops] = useState<number | undefined>(undefined);
  const [maxMbps, setMaxMbps] = useState<number | undefined>(undefined);
  const [expectedIops, setExpectedIops] = useState<number | undefined>(undefined);
  const [peakIops, setPeakIops] = useState<number | undefined>(undefined);

  const {
    data: policies = [],
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "listQosPolicies"],
    queryFn: () =>
      unwrap<{ policies?: QosPolicy[] }>(
        client.queries.adminQuery({ action: "listQosPolicies", params: JSON.stringify({}) }),
      ).then((d) => d?.policies ?? []),
  });

  // Mutation handlers report through their own state, so a failed action is
  // never mistaken for a failed load.
  const loadPolicies = () => void refetch();
  const error = actionError ?? errorMessage(queryError, "Failed to load policies");


  const handleCreate = async () => {
    if (!newName) { setError(t("rmQosNameRequired")); return; }
    try {
      const response = await client.mutations.adminMutation({ action: "createQosPolicy", params: JSON.stringify({
        name: newName, policyType,
        maxIops: policyType === "fixed" ? maxIops : undefined,
        maxMbps: policyType === "fixed" ? maxMbps : undefined,
        expectedIops: policyType === "adaptive" ? expectedIops : undefined,
        peakIops: policyType === "adaptive" ? peakIops : undefined,
      }) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) {
          setResult(`${t("rmQosCreated")}: ${newName}`);
          setShowCreate(false); setNewName("");
          loadPolicies();
        } else setError(data.error || "Failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  const handleDelete = async (uuid: string, name: string) => {
    if (!confirm(t("rmDeleteConfirm").replace("{name}", name))) return;
    try {
      const response = await client.mutations.adminMutation({ action: "deleteQosPolicy", params: JSON.stringify({policyUuid: uuid}) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) { setResult(t("rmDeleted").replace("{name}", name)); loadPolicies(); }
        else setError(data.error || "Failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  if (loading) return <p className="loading">{t("loading")}</p>;

  return (
    <div className="admin-panel">
      <div className="panel-header">
        <h3>{t("rmQosPolicies")}</h3>
        <div className="panel-actions">
          <button onClick={() => setShowCreate(!showCreate)} className="btn-primary">+ {t("rmCreateQos")}</button>
          <button onClick={loadPolicies} className="refresh-btn">↻</button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}
      {result && <div className="success-message">{result}</div>}

      {showCreate && (
        <div className="create-form">
          <div className="form-row">
            <div className="form-group">
              <label>{t("rmQosName")}</label>
              <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="portal_qos_1" />
            </div>
            <div className="form-group">
              <label>{t("rmQosType")}</label>
              <select value={policyType} onChange={(e) => setPolicyType(e.target.value as "fixed" | "adaptive")}>
                <option value="fixed">Fixed</option>
                <option value="adaptive">Adaptive</option>
              </select>
            </div>
          </div>
          {policyType === "fixed" ? (
            <div className="form-row">
              <div className="form-group">
                <label>{t("rmMaxIops")}</label>
                <input type="number" value={maxIops || ""} onChange={(e) => setMaxIops(parseInt(e.target.value) || undefined)} placeholder="10000" />
              </div>
              <div className="form-group">
                <label>{t("rmMaxMbps")}</label>
                <input type="number" value={maxMbps || ""} onChange={(e) => setMaxMbps(parseInt(e.target.value) || undefined)} placeholder="128" />
              </div>
            </div>
          ) : (
            <div className="form-row">
              <div className="form-group">
                <label>{t("rmExpectedIops")}</label>
                <input type="number" value={expectedIops || ""} onChange={(e) => setExpectedIops(parseInt(e.target.value) || undefined)} placeholder="5000" />
              </div>
              <div className="form-group">
                <label>{t("rmPeakIops")}</label>
                <input type="number" value={peakIops || ""} onChange={(e) => setPeakIops(parseInt(e.target.value) || undefined)} placeholder="15000" />
              </div>
            </div>
          )}
          <button onClick={handleCreate} className="btn-primary">{t("rmCreate")}</button>
          <button onClick={() => setShowCreate(false)} className="btn-secondary">{t("cancel")}</button>
        </div>
      )}

      <table className="admin-table">
        <thead><tr><th>{t("rmQosName")}</th><th>{t("rmQosType")}</th><th>{t("rmQosLimits")}</th><th>{t("rmActions")}</th></tr></thead>
        <tbody>
          {policies.map((p) => (
            <tr key={p.uuid}>
              <td>{p.name}</td>
              <td><span className="badge">{p.type}</span></td>
              <td>
                {p.type === "fixed"
                  ? `${p.maxThroughputIops ? p.maxThroughputIops + " IOPS" : ""}${p.maxThroughputIops && p.maxThroughputMbps ? " / " : ""}${p.maxThroughputMbps ? p.maxThroughputMbps + " MB/s" : ""}`
                  : `${p.expectedIops || "—"} / ${p.peakIops || "—"} IOPS`}
              </td>
              <td><button onClick={() => handleDelete(p.uuid, p.name)} className="btn-sm btn-danger">✕</button></td>
            </tr>
          ))}
          {policies.length === 0 && <tr><td colSpan={4} className="empty-state">{t("rmNoQos")}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
