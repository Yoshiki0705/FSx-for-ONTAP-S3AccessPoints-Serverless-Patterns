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

interface ExportPolicy { id: number; name: string; ruleCount: number; }
interface ExportRule { index: number; clients: string[]; roRule: string[]; rwRule: string[]; superuser: string[]; protocols: string[]; }

/**
 * Export Policy Manager — View policies and manage NFS access rules.
 * System Manager-style: policy list → drill into rules → add/remove rules.
 */
export function ExportPolicyManager() {
  const { t } = useTranslation();
  const [policies, setPolicies] = useState<ExportPolicy[]>([]);
  const [selectedPolicy, setSelectedPolicy] = useState<ExportPolicy | null>(null);
  const [rules, setRules] = useState<ExportRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [showAddRule, setShowAddRule] = useState(false);
  const [showCreatePolicy, setShowCreatePolicy] = useState(false);
  const [newPolicyName, setNewPolicyName] = useState("");
  const [newClient, setNewClient] = useState("0.0.0.0/0");
  const [newProtocol, setNewProtocol] = useState("any");
  const [newRoRule, setNewRoRule] = useState("sys");
  const [newRwRule, setNewRwRule] = useState("sys");
  const [newSuperuser, setNewSuperuser] = useState("sys");

  const loadPolicies = async () => {
    setLoading(true);
    try {
      const response = await (client.queries as any).adminQuery({ action: "listExportPolicies", params: JSON.stringify({}) });
      const data = parseResponse<{ policies?: ExportPolicy[]; error?: string }>(response);
      if (data) {
        if (data.error) setError(data.error);
        else setPolicies(data.policies || []);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Load failed"); }
    finally { setLoading(false); }
  };

  const loadRules = async (policyId: string) => {
    setLoading(true);
    try {
      const response = await (client.queries as any).adminQuery({ action: "getExportPolicyRules", params: JSON.stringify({policyId}) });
      const data = parseResponse<{ rules?: ExportRule[]; error?: string }>(response);
      if (data) {
        if (data.error) setError(data.error);
        else setRules(data.rules || []);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Load failed"); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadPolicies(); }, []);

  const handleCreatePolicy = async () => {
    if (!newPolicyName.trim()) { setError(t("rmPolicyNameRequired")); return; }
    setError(null);
    try {
      const response = await (client.mutations as any).adminMutation({
        action: "createExportPolicy",
        params: JSON.stringify({ name: newPolicyName.trim() }),
      });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) {
          setResult(t("rmPolicyCreated"));
          setShowCreatePolicy(false);
          setNewPolicyName("");
          setTimeout(() => setResult(null), 3000);
          loadPolicies();
        } else setError(data.error || "Create failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Create failed"); }
  };

  const handleDeletePolicy = async (policy: ExportPolicy) => {
    if (!confirm(t("rmDeleteConfirm").replace("{name}", policy.name))) return;
    setError(null);
    try {
      const response = await (client.mutations as any).adminMutation({
        action: "deleteExportPolicy",
        params: JSON.stringify({ policyId: String(policy.id), confirm: true }),
      });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) {
          setResult(t("rmDeleted").replace("{name}", policy.name));
          setTimeout(() => setResult(null), 3000);
          loadPolicies();
        } else setError(data.error || "Delete failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Delete failed"); }
  };

  const selectPolicy = (policy: ExportPolicy) => {
    setSelectedPolicy(policy);
    setError(null); setResult(null);
    const policyId = String(policy.id);
    if (!policyId || policyId === "undefined" || policyId === "null" || policyId === "0") {
      setError("policyId is required");
      return;
    }
    loadRules(policyId);
  };

  const handleAddRule = async () => {
    if (!selectedPolicy || !newClient) return;
    try {
      const response = await (client.mutations as any).adminMutation({ action: "createExportPolicyRule", params: JSON.stringify({
        policyId: String(selectedPolicy.id),
        clientMatch: newClient,
        roRule: [newRoRule],
        rwRule: [newRwRule],
        superuser: [newSuperuser],
        protocols: [newProtocol],
      }) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) {
          setResult(t("rmRuleCreated"));
          setShowAddRule(false); setNewClient("0.0.0.0/0");
          setNewProtocol("any"); setNewRoRule("sys"); setNewRwRule("sys"); setNewSuperuser("sys");
          loadRules(String(selectedPolicy.id));
        } else setError(data.error || "Failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  const handleDeleteRule = async (ruleIndex: number) => {
    if (!selectedPolicy) return;
    if (!confirm(t("rmDeleteRuleConfirm").replace("{index}", String(ruleIndex)))) return;
    try {
      const response = await (client.mutations as any).adminMutation({ action: "deleteExportPolicyRule", params: JSON.stringify({
        policyId: String(selectedPolicy.id), ruleIndex,
      }) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) { setResult(t("rmRuleDeleted")); loadRules(String(selectedPolicy.id)); }
        else setError(data.error || "Failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  if (loading && !selectedPolicy) return <p className="loading">{t("loading")}</p>;

  return (
    <div className="admin-panel">
      <div className="panel-header">
        <h3>{selectedPolicy ? `${t("rmExportPolicies")}: ${selectedPolicy.name}` : t("rmExportPolicies")}</h3>
        {selectedPolicy && (
          <button onClick={() => { setSelectedPolicy(null); setRules([]); }} className="btn-secondary">
            ← {t("rmBackToList")}
          </button>
        )}
        <button onClick={selectedPolicy ? () => loadRules(String(selectedPolicy.id)) : loadPolicies} className="refresh-btn">↻</button>
      </div>

      {error && <div className="error-message">{error}</div>}
      {result && <div className="success-message">{result}</div>}

      {!selectedPolicy ? (
        <>
          <div className="panel-actions" style={{ marginBottom: "1rem" }}>
            <button onClick={() => setShowCreatePolicy(!showCreatePolicy)} className="btn-primary">
              + {t("rmCreatePolicy")}
            </button>
          </div>

          {showCreatePolicy && (
            <div className="create-form">
              <div className="form-row">
                <div className="form-group">
                  <label>{t("rmPolicyName")}</label>
                  <input type="text" value={newPolicyName} onChange={(e) => setNewPolicyName(e.target.value)}
                    placeholder="my_export_policy" />
                  <small>{t("rmPolicyNameHint")}</small>
                </div>
              </div>
              <button onClick={handleCreatePolicy} className="btn-primary">{t("rmCreate")}</button>
              <button onClick={() => setShowCreatePolicy(false)} className="btn-secondary">{t("cancel")}</button>
            </div>
          )}

          <table className="admin-table">
            <thead><tr><th>{t("rmPolicyName")}</th><th>{t("rmRuleCount")}</th><th>{t("rmActions")}</th></tr></thead>
            <tbody>
              {policies.map((p) => (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  <td>{p.ruleCount}</td>
                  <td className="action-cell">
                    <button onClick={() => selectPolicy(p)} className="btn-sm">{t("rmViewRules")}</button>
                    {p.name !== "default" && (
                      <button onClick={() => handleDeletePolicy(p)} className="btn-sm btn-danger" title={t("rmDelete")}>✕</button>
                    )}
                  </td>
                </tr>
              ))}
              {policies.length === 0 && <tr><td colSpan={3} className="empty-state">{t("rmNoPolicies")}</td></tr>}
            </tbody>
          </table>
        </>
      ) : (
        <>
          <div className="panel-actions" style={{ marginBottom: "1rem" }}>
            <button onClick={() => setShowAddRule(!showAddRule)} className="btn-primary">+ {t("rmAddRule")}</button>
          </div>

          {showAddRule && (
            <div className="create-form">
              <div className="form-row">
                <div className="form-group">
                  <label>{t("rmClientMatch")}</label>
                  <input type="text" value={newClient} onChange={(e) => setNewClient(e.target.value)}
                    placeholder="10.0.0.0/16" />
                  <small>{t("rmClientMatchHint")}</small>
                </div>
                <div className="form-group">
                  <label>{t("rmProtocol")}</label>
                  <select value={newProtocol} onChange={(e) => setNewProtocol(e.target.value)}>
                    <option value="any">Any</option>
                    <option value="nfs">NFS (all versions)</option>
                    <option value="nfs3">NFSv3</option>
                    <option value="nfs4">NFSv4</option>
                    <option value="cifs">CIFS/SMB</option>
                    <option value="flexcache">FlexCache</option>
                  </select>
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>{t("rmRoRule")}</label>
                  <select value={newRoRule} onChange={(e) => setNewRoRule(e.target.value)}>
                    <option value="sys">sys (UNIX)</option>
                    <option value="any">any (all)</option>
                    <option value="none">none (deny)</option>
                    <option value="never">never (always deny)</option>
                    <option value="krb5">krb5 (Kerberos)</option>
                    <option value="ntlm">ntlm (Windows)</option>
                  </select>
                  <small>Read-only access security</small>
                </div>
                <div className="form-group">
                  <label>{t("rmRwRule")}</label>
                  <select value={newRwRule} onChange={(e) => setNewRwRule(e.target.value)}>
                    <option value="sys">sys (UNIX)</option>
                    <option value="any">any (all)</option>
                    <option value="none">none (deny)</option>
                    <option value="never">never (always deny)</option>
                    <option value="krb5">krb5 (Kerberos)</option>
                    <option value="ntlm">ntlm (Windows)</option>
                  </select>
                  <small>Read-write access security</small>
                </div>
                <div className="form-group">
                  <label>{t("rmSuperuser")}</label>
                  <select value={newSuperuser} onChange={(e) => setNewSuperuser(e.target.value)}>
                    <option value="sys">sys (allow root)</option>
                    <option value="any">any (all root)</option>
                    <option value="none">none (squash root)</option>
                    <option value="krb5">krb5 (Kerberos root)</option>
                  </select>
                  <small>Root (UID 0) access</small>
                </div>
              </div>
              <button onClick={handleAddRule} className="btn-primary">{t("rmCreate")}</button>
              <button onClick={() => setShowAddRule(false)} className="btn-secondary">{t("cancel")}</button>
            </div>
          )}

          <table className="admin-table">
            <thead><tr><th>#</th><th>{t("rmClients")}</th><th>RO</th><th>RW</th><th>Superuser</th><th>{t("rmActions")}</th></tr></thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.index}>
                  <td>{r.index}</td>
                  <td>{r.clients.join(", ")}</td>
                  <td><code>{r.roRule.join(",")}</code></td>
                  <td><code>{r.rwRule.join(",")}</code></td>
                  <td><code>{r.superuser.join(",")}</code></td>
                  <td><button onClick={() => handleDeleteRule(r.index)} className="btn-sm btn-danger">✕</button></td>
                </tr>
              ))}
              {rules.length === 0 && <tr><td colSpan={6} className="empty-state">{t("rmNoRules")}</td></tr>}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
