import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";
import { useIncidentState } from "../hooks/useIncidentState";
import { parseResponse } from "../utils/parseResponse";

const client = generateClient<Schema>();

// Parse the JSON string response from generic dispatch endpoints

interface ActiveBlock {
  pattern?: string;
  index?: number;
  replacement?: string;
  policy?: string;
  rule_index?: number;
  client_match?: string;
  /**
   * When the block is due to be lifted, or null for an indefinite one.
   *
   * ONTAP rules carry no timestamp, so this comes from the portal's ledger.
   * A block placed outside the portal has no row and reports
   * `managedByPortal: false` — the scheduled sweep will not lift it.
   */
  expiresAt?: string | null;
  managedByPortal?: boolean;
  /** Present when the listing covered more than one SVM. */
  svm?: string;
}

interface SvmSummary {
  name: string;
  state?: string;
}

/**
 * Names the SVMs an action reached, when it reached more than one.
 *
 * On a fan-out the operator needs to know which SVMs are now contained, because
 * that is the list they will have to lift later.
 */
function scopeSuffix(data: { fannedOut?: boolean; succeededOn?: string[] }): string {
  if (!data.fannedOut || !data.succeededOn?.length) return "";
  return ` (${data.succeededOn.join(", ")})`;
}

/**
 * Expiry state of one block.
 *
 * Three distinct cases, and collapsing any two of them would mislead:
 * an expiry the sweep will act on, an indefinite block the portal owns, and a
 * block placed outside the portal that the sweep deliberately leaves alone.
 */
function BlockExpiry({ block }: { block: ActiveBlock }) {
  const { t } = useTranslation();

  if (!block.managedByPortal) {
    return (
      <span className="block-expiry block-expiry-unmanaged" title={t("arpResponseUnmanagedHint")}>
        {t("arpResponseUnmanaged")}
      </span>
    );
  }
  if (!block.expiresAt) {
    return <span className="block-expiry block-expiry-indefinite">{t("arpResponseNoExpiry")}</span>;
  }
  return (
    <span className="block-expiry">
      {t("arpResponseExpiresAt")}: {new Date(block.expiresAt).toLocaleString()}
    </span>
  );
}

/** Containment actions that require an explicit confirmation before running. */
type ConfirmAction = "contain" | "blockSmb" | "blockNfs" | "disconnect";

interface ArpResponseActionsProps {
  /** Current ARP threat level — controls visibility of containment actions */
  threatLevel: string;
  /** Volume name for snapshot creation */
  volumeName: string;
}

/**
 * ARP/AI Response Actions — Isolation and Containment controls.
 *
 * Provides portal-native containment actions equivalent to DII Storage
 * Workload Security, executed via ONTAP REST API:
 * - Block SMB User (name-mapping deny)
 * - Block NFS IP (export-policy deny rule)
 * - Full Containment (snapshot + block + disconnect)
 * - View Active Blocks
 * - Unblock (remove isolation)
 *
 * These mutations require the "storage-admin" Cognito group.
 * Regular users see the ARP status (read-only) but not action buttons.
 *
 * Architecture:
 *   AppSync mutation → ArpResponseLambdaDataSource → VPC Lambda
 *   → ONTAP REST API (management LIF)
 */
export function ArpResponseActions({ threatLevel, volumeName }: ArpResponseActionsProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<"contain" | "blocks" | "unblock">("contain");
  const { incident, markContained, markInvestigating, markResolved } = useIncidentState(volumeName || "default");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [domain, setDomain] = useState("");
  const [username, setUsername] = useState("");
  const [clientIp, setClientIp] = useState("");
  const [reason, setReason] = useState("");
  // Hours until the block lifts itself. 0 means indefinite, which stays
  // available but has to be chosen — an expiry that must be requested is one
  // that gets forgotten, and a forgotten block reads as an outage.
  const [ttlHours, setTtlHours] = useState(24);

  // Which SVMs the action targets. Empty means the deployment's default SVM
  // only. A compromised account is usually reachable on every SVM that trusts
  // the same directory, so containing it one at a time leaves the rest open for
  // as long as that takes — but widening the blast radius stays a choice.
  const [svms, setSvms] = useState<SvmSummary[]>([]);
  const [selectedSvms, setSelectedSvms] = useState<string[]>([]);

  /** SVM scope for a request, omitted entirely when the default is wanted. */
  const svmScope = () => (selectedSvms.length > 0 ? { svms: selectedSvms } : {});

  // Active blocks state
  const [smbBlocks, setSmbBlocks] = useState<ActiveBlock[]>([]);
  const [nfsBlocks, setNfsBlocks] = useState<ActiveBlock[]>([]);
  const [blocksLoading, setBlocksLoading] = useState(false);

  // Pending containment action awaiting confirmation. Blocking cuts data access
  // for a principal across the whole SVM and nothing expires it automatically,
  // so the operator states the intent twice. The backend enforces the same gate.
  const [pending, setPending] = useState<ConfirmAction | null>(null);

  const clearForm = () => {
    setDomain("");
    setUsername("");
    setClientIp("");
    setReason("");
    setError(null);
    setResult(null);
  };

  // Load active blocks
  const loadActiveBlocks = async () => {
    setBlocksLoading(true);
    try {
      const response = await client.queries.arpQuery({ action: "listActiveBlocks", params: JSON.stringify({...svmScope()}) });
      const data = parseResponse<{
        smbBlocks?: ActiveBlock[];
        nfsBlocks?: ActiveBlock[];
        total?: number;
        error?: string;
      }>(response);
      if (data) {
        // Previously this branched on error string length, to hide a backend
        // message that was literally "4" — an IndexError whose text was a bare
        // number. That guess also swallowed any genuinely short error, and the
        // backend now reports the exception type instead, so the response is
        // taken at face value: report failures, render successes.
        if (data.error) {
          setError(data.error);
          setSmbBlocks([]);
          setNfsBlocks([]);
        } else {
          setSmbBlocks(data.smbBlocks || []);
          setNfsBlocks(data.nfsBlocks || []);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load active blocks");
    } finally {
      setBlocksLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "blocks") {
      loadActiveBlocks();
    }
  }, [activeTab, selectedSvms]);

  // Load the SVM list once, so the operator can widen the scope deliberately.
  // A failure here is not surfaced as an error: it only means the picker is
  // unavailable, and containment on the default SVM still works.
  useEffect(() => {
    (async () => {
      try {
        const response = await client.queries.arpQuery({
          action: "listSvms",
          params: JSON.stringify({}),
        });
        const data = parseResponse<{ success?: boolean; svms?: SvmSummary[] }>(response);
        if (data?.success && data.svms) setSvms(data.svms);
      } catch {
        // Picker stays hidden; the default SVM is still targetable.
      }
    })();
  }, []);

  const toggleSvm = (name: string) => {
    setSelectedSvms((current) =>
      current.includes(name) ? current.filter((s) => s !== name) : [...current, name]
    );
  };

  // --- Action: Full Containment ---
  const handleContainThreat = async () => {
    if (!domain && !username && !clientIp) {
      setError(t("arpResponseRequireTarget"));
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await client.mutations.arpMutation({ action: "containThreat", params: JSON.stringify({
        domain: domain || undefined,
        username: username || undefined,
        clientIp: clientIp || undefined,
        volumeName: volumeName || undefined,
        reason: reason || "portal-initiated",
        confirm: true,
        ttlHours,
        ...svmScope(),
      }) });

      const data = parseResponse<{ success?: boolean; status?: string; steps?: unknown; error?: string; fannedOut?: boolean; succeededOn?: string[] }>(response);
      if (data) {
        if (data.success) {
          setResult(t("arpResponseContained") + scopeSuffix(data));
          markContained(undefined, [username], [clientIp].filter(Boolean));
          clearForm();
        } else {
          setError(data.error || t("arpResponsePartialFailure"));
        }
      } else if (response.errors) {
        setError(response.errors.map((e) => e.message).join(", "));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Containment failed");
    } finally {
      setLoading(false);
    }
  };

  // --- Action: Block SMB User ---
  const handleBlockSmbUser = async () => {
    if (!domain || !username) {
      setError(t("arpResponseDomainUserRequired"));
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await client.mutations.arpMutation({ action: "blockSmbUser", params: JSON.stringify({domain, username, confirm: true, ttlHours, ...svmScope()}) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) {
          setResult(`${t("arpResponseBlocked")}: ${domain}\\${username}`);
        } else {
          setError(data.error || "Block failed");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Block failed");
    } finally {
      setLoading(false);
    }
  };

  // --- Action: Block NFS IP ---
  const handleBlockNfsIp = async () => {
    if (!clientIp) {
      setError(t("arpResponseIpRequired"));
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await client.mutations.arpMutation({ action: "blockNfsIp", params: JSON.stringify({clientIp, confirm: true, ttlHours, ...svmScope()}) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) {
          setResult(`${t("arpResponseBlocked")}: ${clientIp}`);
        } else {
          setError(data.error || "Block failed");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Block failed");
    } finally {
      setLoading(false);
    }
  };

  // --- Action: Disconnect SMB sessions ---
  //
  // Blocking a user only stops the next authentication — an already-open SMB
  // session keeps working until it is dropped. This exists as its own action so
  // an operator can cut live sessions without re-running the whole containment.
  const handleDisconnectSessions = async () => {
    if (!domain || !username) {
      if (!clientIp) {
        setError(t("arpResponseRequireTarget"));
        return;
      }
    }
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await client.mutations.arpMutation({ action: "disconnectSessions", params: JSON.stringify({
        user: domain && username ? `${domain}\\${username}` : undefined,
        clientIp: clientIp || undefined,
        confirm: true,
      }) });
      const data = parseResponse<{ success?: boolean; disconnected?: number; error?: string }>(response);
      if (data) {
        if (data.success) {
          setResult(`${t("arpResponseDisconnected")}: ${data.disconnected ?? 0}`);
        } else {
          setError(data.error || "Disconnect failed");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Disconnect failed");
    } finally {
      setLoading(false);
    }
  };

  // Confirmation descriptions are per-action because the consequences differ:
  // an NFS block is subject to client-side caching, an SMB block is not, and a
  // disconnect on its own does not prevent the next login.
  const confirmMessage = (action: ConfirmAction): string => {
    switch (action) {
      case "contain": return t("arpResponseConfirmContain");
      case "blockSmb": return t("arpResponseConfirmBlockSmb");
      case "blockNfs": return t("arpResponseConfirmBlockNfs");
      case "disconnect": return t("arpResponseConfirmDisconnect");
    }
  };

  const runPending = async () => {
    const action = pending;
    setPending(null);
    if (!action) return;
    if (action === "contain") await handleContainThreat();
    else if (action === "blockSmb") await handleBlockSmbUser();
    else if (action === "blockNfs") await handleBlockNfsIp();
    else if (action === "disconnect") await handleDisconnectSessions();
  };

  // --- Action: Unblock SMB User ---
  const handleUnblockSmbUser = async (pattern: string, svm?: string) => {
    const parts = pattern.split("\\\\");
    if (parts.length < 2) return;
    const [dom, user] = [parts[0], parts.slice(1).join("\\")];

    setLoading(true);
    try {
      // The SVM comes from the listed block, not from the current selection: the
      // block lives on one specific SVM, and lifting it anywhere else would
      // leave it in place while reporting success.
      const response = await client.mutations.arpMutation({ action: "unblockSmbUser", params: JSON.stringify({domain: dom, username: user, ...(svm ? { svm } : {})}) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) {
          setResult(`${t("arpResponseUnblocked")}: ${pattern}`);
          loadActiveBlocks();
        } else {
          setError(data.error || "Unblock failed");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unblock failed");
    } finally {
      setLoading(false);
    }
  };

  // --- Action: Unblock NFS IP ---
  const handleUnblockNfsIp = async (ipMatch: string, svm?: string) => {
    const ip = ipMatch.replace("fsxn_auto_response,", "");
    setLoading(true);
    try {
      const response = await client.mutations.arpMutation({ action: "unblockNfsIp", params: JSON.stringify({clientIp: ip, ...(svm ? { svm } : {})}) });
      const data = parseResponse<{ success?: boolean; error?: string }>(response);
      if (data) {
        if (data.success) {
          setResult(`${t("arpResponseUnblocked")}: ${ip}`);
          loadActiveBlocks();
        } else {
          setError(data.error || "Unblock failed");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unblock failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="arp-response-section">
      <h3>{t("arpResponseTitle")}</h3>

      {/* Incident lifecycle state badge */}
      {incident.state !== "none" && (
        <div className={`incident-badge incident-${incident.state}`}>
          {incident.state === "detected" && `🔴 ${t("incidentDetected")}`}
          {incident.state === "contained" && `🟠 ${t("incidentContained")}`}
          {incident.state === "investigating" && `🟡 ${t("incidentInvestigating")}`}
          {incident.state === "resolved" && `🟢 ${t("incidentResolved")}`}
          {(incident.state === "contained" || incident.state === "investigating") && (
            <button className="btn-sm" style={{ marginLeft: "0.5rem" }} onClick={() => {
              if (incident.state === "contained") markInvestigating();
              else markResolved();
            }}>
              {incident.state === "contained"
                ? `→ ${t("incidentToInvestigating")}`
                : `→ ${t("incidentToResolved")}`}
            </button>
          )}
        </div>
      )}

      {/* Threat-level-aware banner */}
      {(threatLevel === "high" || threatLevel === "moderate") && (
        <div className="arp-response-alert" role="alert">
          <span className="alert-icon">⚠️</span>
          <span>{t("arpResponseAlertActive")}</span>
        </div>
      )}

      {/* Tab navigation */}
      <div className="arp-response-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={activeTab === "contain"}
          className={activeTab === "contain" ? "tab-active" : ""}
          onClick={() => { setActiveTab("contain"); setError(null); setResult(null); }}
        >
          {t("arpResponseTabContain")}
        </button>
        <button
          role="tab"
          aria-selected={activeTab === "blocks"}
          className={activeTab === "blocks" ? "tab-active" : ""}
          onClick={() => { setActiveTab("blocks"); setError(null); setResult(null); }}
        >
          {t("arpResponseTabBlocks")}
        </button>
      </div>

      {/* Status messages */}
      {error && <div className="error-message" role="alert">{error}</div>}
      {result && <div className="success-message" role="status">{result}</div>}

      {/* Contain tab */}
      {activeTab === "contain" && (
        <div className="arp-response-form">
          <p className="form-description">{t("arpResponseContainDesc")}</p>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="arp-domain">{t("arpResponseDomain")}</label>
              <input
                id="arp-domain"
                type="text"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="CORP"
                disabled={loading}
              />
            </div>
            <div className="form-group">
              <label htmlFor="arp-username">{t("arpResponseUsername")}</label>
              <input
                id="arp-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="jdoe"
                disabled={loading}
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="arp-ip">{t("arpResponseClientIp")}</label>
            <input
              id="arp-ip"
              type="text"
              value={clientIp}
              onChange={(e) => setClientIp(e.target.value)}
              placeholder="10.0.5.99"
              disabled={loading}
            />
          </div>

          <div className="form-group">
            <label htmlFor="arp-reason">{t("arpResponseReason")}</label>
            <input
              id="arp-reason"
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={t("arpResponseReasonPlaceholder")}
              disabled={loading}
            />
          </div>

          {svms.length > 1 && (
            <fieldset className="form-group arp-svm-scope">
              <legend>{t("arpResponseSvmScopeLabel")}</legend>
              {svms.map((svm) => {
                const stopped = svm.state && svm.state !== "running";
                return (
                  <label key={svm.name} className="arp-svm-option">
                    <input
                      type="checkbox"
                      checked={selectedSvms.includes(svm.name)}
                      onChange={() => toggleSvm(svm.name)}
                      disabled={loading || !!stopped}
                    />
                    {svm.name}
                    {stopped && <span className="arp-svm-stopped"> ({svm.state})</span>}
                  </label>
                );
              })}
              <p className="form-note">
                {selectedSvms.length === 0
                  ? t("arpResponseSvmScopeDefault")
                  : t("arpResponseSvmScopeSelected").replace("{count}", String(selectedSvms.length))}
              </p>
            </fieldset>
          )}

          <div className="form-group">
            <label htmlFor="arp-ttl">{t("arpResponseTtlLabel")}</label>
            <select
              id="arp-ttl"
              value={ttlHours}
              onChange={(e) => setTtlHours(Number(e.target.value))}
              disabled={loading}
            >
              <option value={1}>{t("arpResponseTtl1h")}</option>
              <option value={4}>{t("arpResponseTtl4h")}</option>
              <option value={24}>{t("arpResponseTtl24h")}</option>
              <option value={72}>{t("arpResponseTtl72h")}</option>
              <option value={168}>{t("arpResponseTtl7d")}</option>
              <option value={0}>{t("arpResponseTtlIndefinite")}</option>
            </select>
            <p className="form-note">
              {ttlHours === 0 ? t("arpResponseTtlIndefiniteNote") : t("arpResponseTtlNote")}
            </p>
          </div>

          <div className="arp-action-buttons">
            <button
              onClick={() => setPending("contain")}
              disabled={loading || (!domain && !username && !clientIp)}
              className="btn-danger"
              title={t("arpResponseContainTooltip")}
            >
              {loading ? t("processing") : `🛡️ ${t("arpResponseContainBtn")}`}
            </button>
            <button
              onClick={() => setPending("blockSmb")}
              disabled={loading || !domain || !username}
              className="btn-warning"
            >
              {`🚫 ${t("arpResponseBlockSmb")}`}
            </button>
            <button
              onClick={() => setPending("blockNfs")}
              disabled={loading || !clientIp}
              className="btn-warning"
            >
              {`🚫 ${t("arpResponseBlockNfs")}`}
            </button>
            <button
              onClick={() => setPending("disconnect")}
              disabled={loading || (!(domain && username) && !clientIp)}
              className="btn-warning"
            >
              {`🔌 ${t("arpResponseDisconnect")}`}
            </button>
          </div>

          {pending && (
            <div className="arp-confirm-row" role="alertdialog" aria-label={t("arpResponseConfirmTitle")}>
              <p className="arp-confirm-title">{t("arpResponseConfirmTitle")}</p>
              <p className="arp-confirm-detail">{confirmMessage(pending)}</p>
              <div className="arp-confirm-actions">
                <button onClick={runPending} disabled={loading} className="btn-danger">
                  {t("arpResponseConfirmRun")}
                </button>
                <button onClick={() => setPending(null)} disabled={loading} className="btn-sm">
                  {t("arpResponseConfirmCancel")}
                </button>
              </div>
            </div>
          )}

          <p className="form-note">{t("arpResponseAdminOnly")}</p>
          <p className="form-note">{t("arpResponseSweepNote")}</p>
        </div>
      )}

      {/* Active Blocks tab */}
      {activeTab === "blocks" && (
        <div className="arp-blocks-list">
          {blocksLoading ? (
            <p className="loading">{t("loading")}</p>
          ) : (
            <>
              <div className="blocks-section">
                <h4>{t("arpResponseSmbBlocks")} ({smbBlocks.length})</h4>
                {smbBlocks.length === 0 ? (
                  <p className="empty-state">{t("arpResponseNoBlocks")}</p>
                ) : (
                  <ul className="blocks-list">
                    {smbBlocks.map((block, i) => (
                      <li key={`smb-${i}`} className="block-item">
                        <span className="block-pattern">{block.pattern}</span>
                        {block.svm && <span className="block-svm">{block.svm}</span>}
                        <BlockExpiry block={block} />
                        <button
                          onClick={() => handleUnblockSmbUser(block.pattern || "", block.svm)}
                          disabled={loading}
                          className="btn-unblock"
                        >
                          {t("arpResponseUnblock")}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="blocks-section">
                <h4>{t("arpResponseNfsBlocks")} ({nfsBlocks.length})</h4>
                {nfsBlocks.length === 0 ? (
                  <p className="empty-state">{t("arpResponseNoBlocks")}</p>
                ) : (
                  <ul className="blocks-list">
                    {nfsBlocks.map((block, i) => (
                      <li key={`nfs-${i}`} className="block-item">
                        <span className="block-pattern">
                          {block.client_match?.replace("fsxn_auto_response,", "") || "—"}
                        </span>
                        <span className="block-policy">{block.policy}</span>
                        {block.svm && <span className="block-svm">{block.svm}</span>}
                        <BlockExpiry block={block} />
                        <button
                          onClick={() => handleUnblockNfsIp(block.client_match || "", block.svm)}
                          disabled={loading}
                          className="btn-unblock"
                        >
                          {t("arpResponseUnblock")}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <button onClick={loadActiveBlocks} className="refresh-btn" disabled={blocksLoading}>
                ↻ {t("refresh")}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
