import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage, unwrap } from "../../lib/portalQuery";
import { adminMutate, dispatch } from "../../lib/dispatch";
import type { PolicyUuid } from "../../lib/dispatchActions";
import { VolumeSelector, type VolumeInfo } from "./VolumeSelector";

/** ONTAP's reserved keyword for "no policy". Not a UI placeholder. */
const NO_POLICY = "none";

interface QosPolicy {
  name: string;
  /** ONTAP's policy UUID, branded where it arrives. Not the policy name. */
  uuid: PolicyUuid;
  type: string;
  maxThroughputIops?: number;
  maxThroughputMbps?: number;
  expectedIops?: number;
  peakIops?: number;
}

/**
 * QoS Policy Manager — create, view and delete QoS policies, and assign one to a volume.
 *
 * The assignment half is what makes the delete usable. ONTAP refuses to delete a policy
 * group that a storage object is assigned to, so a panel that can only create and delete
 * is fine until something else assigns a policy, and then the delete stops working with
 * an error that does not say which volume is holding it.
 */
export function QosPolicyManager() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
  const [result, setResult] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  // The volume the assignment row acts on, kept whole for its branded UUID.
  const [volume, setVolume] = useState<VolumeInfo | null>(null);
  const [assignTo, setAssignTo] = useState<string>(NO_POLICY);
  const [assigning, setAssigning] = useState(false);

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
        dispatch("adminQuery", { action: "listQosPolicies" }),
      ).then((d) => d?.policies ?? []),
  });

  // Mutation handlers report through their own state, so a failed action is
  // never mistaken for a failed load.
  const loadPolicies = () => void refetch();
  const error = actionError ?? errorMessage(queryError, "Failed to load policies");

  // The assignment currently in effect, read on its own rather than taken from the
  // selector's list: the list is loaded once and the selector notifies the parent once
  // per volume, so a `VolumeInfo` captured at selection time keeps what it was captured
  // with. Same reason the quota panel reads enforcement separately.
  const assignedQuery = useQuery({
    queryKey: ["admin", "volumeQosPolicy", volume?.uuid ?? null],
    enabled: !!volume,
    queryFn: () =>
      unwrap<{ volume?: { qos?: { policy?: { name?: string } } } }>(
        dispatch("adminQuery", { action: "getVolume", params: { volumeUuid: volume!.uuid } }),
      ).then((d) => d?.volume?.qos?.policy?.name ?? ""),
  });
  const assigned = assignedQuery.data ?? volume?.qosPolicyName ?? "";

  /** Assign the selected policy to the selected volume, or remove the one it has. */
  const handleAssign = async () => {
    if (!volume) return;
    setError(null);
    setAssigning(true);
    try {
      const data = await adminMutate<{ success?: boolean; cleared?: boolean }>({
        action: "assignQosToVolume",
        params: { volumeUuid: volume.uuid, policyName: assignTo },
      });
      if (data?.success) {
        setResult(data.cleared ? t("rmQosUnassigned") : `${t("rmQosAssigned")}: ${assignTo}`);
        setTimeout(() => setResult(null), 4000);
        queryClient.setQueryData(
          ["admin", "volumeQosPolicy", volume.uuid],
          data.cleared ? "" : assignTo,
        );
        // Other panels read the same list, and it now carries the old assignment.
        void queryClient.invalidateQueries({ queryKey: ["admin", "volumeSelector"] });
      } else setError(data?.error || t("rmActionFailed"));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("rmActionFailed"));
    } finally {
      setAssigning(false);
    }
  };


  const handleCreate = async () => {
    if (!newName) { setError(t("rmQosNameRequired")); return; }
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "createQosPolicy",
        params: {
          name: newName, policyType,
          maxIops: policyType === "fixed" ? maxIops : undefined,
          maxMbps: policyType === "fixed" ? maxMbps : undefined,
          expectedIops: policyType === "adaptive" ? expectedIops : undefined,
          peakIops: policyType === "adaptive" ? peakIops : undefined,
        },
      });
      if (data) {
        if (data.success) {
          setResult(`${t("rmQosCreated")}: ${newName}`);
          setShowCreate(false); setNewName("");
          loadPolicies();
        } else setError(data.error || "Failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  const handleDelete = async (uuid: PolicyUuid, name: string) => {
    if (!confirm(t("rmDeleteConfirm").replace("{name}", name))) return;
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "deleteQosPolicy",
        params: { policyUuid: uuid },
      });
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

      {/* Assignment, above the policy table: a policy's row cannot say whether it is in
          use, and ONTAP's refusal to delete an assigned policy does not name the volume
          holding it. */}
      <div className="rm-enforcement-row">
        <VolumeSelector
          label={t("rmQosAssignTo")}
          onSelect={(vol) => {
            setVolume(vol);
            setAssignTo(vol.qosPolicyName || NO_POLICY);
            setActionError(null);
            setResult(null);
          }}
          autoSelectFirst
        />
        {volume && (
          <>
            <span>
              {t("rmQosCurrent")}:{" "}
              <strong className={assigned ? "rm-enforcement-on" : "rm-enforcement-off"}>
                {assigned || t("rmQosNotAssigned")}
              </strong>
            </span>
            <select
              value={assignTo}
              onChange={(e) => setAssignTo(e.target.value)}
              aria-label={t("rmQosAssignTo")}
            >
              {/* The value is ONTAP's keyword, not an empty option: the handler sends it
                  verbatim, and an empty string is refused there. */}
              <option value={NO_POLICY}>{t("rmQosRemoveAssignment")}</option>
              {policies.map((p) => (
                <option key={p.uuid} value={p.name}>
                  {p.name}
                </option>
              ))}
            </select>
            <button
              className="rm-btn-primary"
              disabled={assigning || assignTo === (assigned || NO_POLICY)}
              onClick={() => void handleAssign()}
            >
              {t("rmApply")}
            </button>
            <span className="rm-hint">{t("rmQosAssignHint")}</span>
          </>
        )}
      </div>

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
