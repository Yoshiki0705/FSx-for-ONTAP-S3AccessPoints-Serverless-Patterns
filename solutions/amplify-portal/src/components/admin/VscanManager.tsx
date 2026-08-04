import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";

const client = generateClient<Schema>();

function parseResponse<T>(response: { data?: string | null }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === "string" ? JSON.parse(response.data) : response.data;
  } catch { return null; }
}

interface VscanPolicy {
  name: string;
  enabled: boolean;
  mandatory: boolean;
  maxFileSize: number;
  excludedPaths: string[];
  excludedExtensions: string[];
}

export function VscanManager() {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useState(false);
  const [policies, setPolicies] = useState<VscanPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  /** Name of the policy awaiting delete confirmation. */
  const [confirmFor, setConfirmFor] = useState<string | null>(null);
  /** The setup guide is shown automatically when Vscan is off, and on demand when on. */
  const [showGuide, setShowGuide] = useState(false);
  const [newName, setNewName] = useState("");
  const [newMaxMb, setNewMaxMb] = useState(2048);
  const [newExts, setNewExts] = useState("");
  const [newMandatory, setNewMandatory] = useState(false);

  /** Run a write action, then refresh. */
  const runAction = async (action: string, params: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const resp = await (client.mutations as any).adminMutation({
        action,
        params: JSON.stringify(params),
      });
      const data = parseResponse<{ success?: boolean; error?: string }>(resp);
      if (data?.success) {
        setSuccess(t("vsActionDone"));
        setConfirmFor(null);
        setTimeout(() => setSuccess(null), 4000);
        loadData();
      } else {
        setError(data?.error || "Action failed");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const createPolicy = async () => {
    const exts = newExts
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    await runAction("createVscanPolicy", {
      name: newName.trim(),
      mandatory: newMandatory,
      maxFileSize: newMaxMb * 1024 * 1024,
      excludedExtensions: exts.length > 0 ? exts : undefined,
    });
    setShowCreate(false);
    setNewName("");
    setNewExts("");
  };

  const loadData = async () => {
    setLoading(true); setError(null);
    try {
      const statusResp = await (client.queries as any).adminQuery({
        action: "getVscanStatus", params: JSON.stringify({}),
      });
      const statusData = parseResponse<{
        enabled?: boolean; error?: string
      }>(statusResp);
      if (statusData?.error) {
        // ONTAP not connected or action not deployed yet — show guidance
        setEnabled(false);
      } else if (statusData) {
        setEnabled(statusData.enabled || false);
      }

      const polResp = await (client.queries as any).adminQuery({
        action: "listVscanPolicies", params: JSON.stringify({}),
      });
      const polData = parseResponse<{
        policies?: VscanPolicy[]; error?: string
      }>(polResp);
      // Don't show error for connection/deploy issues — just show empty + guidance
      if (polData?.error && !polData.error.includes("Unknown action") && !polData.error.includes("not configured")) {
        setError(polData.error);
      } else {
        setPolicies(polData?.policies || []);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    } finally { setLoading(false); }
  };

  useEffect(() => { loadData(); }, []);

  // ─── Setup Guidance (shown when Vscan is not enabled) ───
  const renderSetupGuide = () => (
    <div className="vs-setup-guide">
      {/* The "not configured" warning only makes sense while Vscan is off. */}
      {!enabled && (
        <div className="rm-error" style={{ background: "#fff3cd", borderColor: "#ffc107", color: "#856404" }}>
          ⚠️ {t("vsNotConfigured")}
        </div>
      )}

      <div className="vs-guide-section">
        <h4>📋 {t("vsSetupOverview")}</h4>
        <p className="rm-hint">{t("vsSetupOverviewDesc")}</p>
      </div>

      {/* Step 1: Vendor Selection */}
      <div className="vs-guide-section">
        <h4>1. {t("vsStep1Title")}</h4>
        <p className="rm-hint">{t("vsStep1Desc")}</p>
        <table className="rm-table" style={{ fontSize: "0.85rem" }}>
          <thead>
            <tr>
              <th>{t("vsVendor")}</th>
              <th>{t("vsProduct")}</th>
              <th>{t("vsLicense")}</th>
              <th>{t("vsNote")}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="lu-username">Trellix (McAfee)</td>
              <td>VirusScan Enterprise for Storage</td>
              <td>
                <a href="https://www.trellix.com/products/endpoint-security/"
                  target="_blank" rel="noopener noreferrer">
                  Trellix.com →
                </a>
              </td>
              <td>{t("vsNoteTrellix")}</td>
            </tr>
            <tr>
              <td className="lu-username">Trend Micro</td>
              <td>ServerProtect for Storage</td>
              <td>
                <a href="https://www.trendmicro.com/en_us/business/products/user-protection/sps/storage.html"
                  target="_blank" rel="noopener noreferrer">
                  TrendMicro.com →
                </a>
              </td>
              <td>{t("vsNoteTrend")}</td>
            </tr>
            <tr>
              <td className="lu-username">Deep Instinct</td>
              <td>Deep Instinct Prevention for Storage</td>
              <td>
                <a href="https://www.deepinstinct.com/partners/netapp"
                  target="_blank" rel="noopener noreferrer">
                  DeepInstinct.com →
                </a>
              </td>
              <td>{t("vsNoteDeep")}</td>
            </tr>
            <tr>
              <td className="lu-username">Sentinel One</td>
              <td>Singularity for NetApp</td>
              <td>
                <a href="https://www.sentinelone.com/partners/netapp/"
                  target="_blank" rel="noopener noreferrer">
                  SentinelOne.com →
                </a>
              </td>
              <td>{t("vsNoteSentinel")}</td>
            </tr>
            <tr>
              <td className="lu-username">Symantec (Broadcom)</td>
              <td>Protection Engine for NAS</td>
              <td>
                <a href="https://www.broadcom.com/products/cybersecurity/endpoint"
                  target="_blank" rel="noopener noreferrer">
                  Broadcom.com →
                </a>
              </td>
              <td>{t("vsNoteSymantec")}</td>
            </tr>
            <tr>
              <td className="lu-username">OPSWAT</td>
              <td>MetaDefender for Secure Storage</td>
              <td>
                <a href="https://www.opswat.com/products/metadefender/secure-storage"
                  target="_blank" rel="noopener noreferrer">
                  OPSWAT.com →
                </a>
              </td>
              <td>{t("vsNoteOpswat")}</td>
            </tr>
          </tbody>
        </table>
        <p className="rm-hint">
          <a href="https://docs.netapp.com/us-en/ontap/antivirus/vscan-partner-solutions.html"
            target="_blank" rel="noopener noreferrer">
            📚 {t("vsPartnerDocsLink")}
          </a>
          {" | "}
          <a href="https://mysupport.netapp.com/matrix/"
            target="_blank" rel="noopener noreferrer">
            🔍 {t("vsImtLink")}
          </a>
        </p>
      </div>

      {/* Step 2: Download Antivirus Connector */}
      <div className="vs-guide-section">
        <h4>2. {t("vsStep2Title")}</h4>
        <p className="rm-hint">{t("vsStep2Desc")}</p>
        <div className="vs-link-card">
          <a href="https://mysupport.netapp.com/site/products/all/details/ontap-antivirus-connector/downloads-tab"
            target="_blank" rel="noopener noreferrer"
            className="rm-btn-primary" style={{ textDecoration: "none", display: "inline-block" }}>
            ⬇️ {t("vsDownloadConnector")}
          </a>
          <span className="rm-hint" style={{ marginLeft: "0.5rem" }}>
            ({t("vsRequiresNss")})
          </span>
        </div>
        <p className="rm-hint">{t("vsStep2Requirements")}</p>
      </div>

      {/* Step 3: Deploy EC2 + Install */}
      <div className="vs-guide-section">
        <h4>3. {t("vsStep3Title")}</h4>
        <p className="rm-hint">{t("vsStep3Desc")}</p>
        <div className="vs-code-block">
          <pre>{t("vsStep3Architecture")}</pre>
        </div>
        <p className="rm-hint">
          <a href="https://aws.amazon.com/blogs/storage/securing-your-amazon-fsx-for-ontap-windows-share-smb-against-viruses/"
            target="_blank" rel="noopener noreferrer">
            📖 {t("vsAwsBlogLink")}
          </a>
          {" | "}
          <a href="https://github.com/aws-samples/securing-amazon-fsx-for-ontap-against-viruses"
            target="_blank" rel="noopener noreferrer">
            💻 {t("vsGitHubSampleLink")}
          </a>
        </p>
      </div>

      {/* Step 4: ONTAP CLI configuration */}
      <div className="vs-guide-section">
        <h4>4. {t("vsStep4Title")}</h4>
        <p className="rm-hint">{t("vsStep4Desc")}</p>
        <div className="vs-code-block">
          <pre>{`# Scanner pool creation
vserver vscan scanner-pool create \\
  -vserver <svm-name> \\
  -scanner-pool vscan_pool1 \\
  -hostnames <ec2-hostname> \\
  -privileged-users <domain>\\\\<vscan-user>

# On-access policy creation
vserver vscan on-access-policy create \\
  -vserver <svm-name> \\
  -policy-name vscan_policy1 \\
  -protocol cifs \\
  -max-file-size 2GB \\
  -filters scan-mandatory

# Enable Vscan
vserver vscan enable -vserver <svm-name>`}</pre>
        </div>
        <p className="rm-hint">
          <a href="https://docs.netapp.com/us-en/ontap/antivirus/install-ontap-antivirus-connector-task.html"
            target="_blank" rel="noopener noreferrer">
            📚 {t("vsInstallGuideLink")}
          </a>
          {" | "}
          <a href="https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/Antiviurs_Vscan_setup_and_troubleshooting_for_ONTAP"
            target="_blank" rel="noopener noreferrer">
            🔧 {t("vsTroubleshootLink")}
          </a>
        </p>
      </div>

      {/* Step 5: Verify in this panel */}
      <div className="vs-guide-section">
        <h4>5. {t("vsStep5Title")}</h4>
        <p className="rm-hint">{t("vsStep5Desc")}</p>
      </div>
    </div>
  );

  // ─── Main Render ───
  return (
    <div className="vscan-manager">
      {error && <div className="rm-error">⚠️ {error}</div>}
      {success && <div className="rm-success">✅ {success}</div>}

      {loading ? (
        <div className="rm-loading">{t("ontapConnecting")}</div>
      ) : (
        <>
          <div className="lu-toolbar">
            <span className="lu-count">
              Vscan:{" "}
              <span className={`lu-badge ${enabled ? "active" : "disabled"}`}>
                {enabled ? t("vsEnabled") : t("vsDisabled")}
              </span>
            </span>
            <button
              className={enabled ? "rm-btn-danger-sm" : "rm-btn-primary"}
              disabled={busy}
              onClick={() => runAction("setVscanEnabled", { enabled: !enabled })}
            >
              {enabled ? t("vsDisableBtn") : t("vsEnableBtn")}
            </button>
            {enabled && (
              <>
                <button className="rm-btn-sm" onClick={loadData}>
                  🔄 {t("rmApply")}
                </button>
                {/* The scanner-side setup steps stay useful after Vscan is on, so keep
                    them reachable rather than only showing them while it is off. */}
                <button className="rm-btn-sm" onClick={() => setShowGuide((v) => !v)}>
                  📖 {showGuide ? t("vsHideSetupGuide") : t("vsShowSetupGuide")}
                </button>
              </>
            )}
          </div>

          {!enabled ? (
            renderSetupGuide()
          ) : (
            <>
              {showGuide && renderSetupGuide()}
              <div className="lu-toolbar" style={{ marginTop: "1rem" }}>
                <h4 style={{ margin: 0 }}>📋 {t("vsPolicies")}</h4>
                <button
                  className="rm-btn-primary"
                  disabled={busy}
                  onClick={() => setShowCreate((v) => !v)}
                >
                  + {t("vsCreatePolicy")}
                </button>
              </div>

              {showCreate && (
                <div className="rm-form">
                  <h4>{t("vsCreatePolicy")}</h4>
                  <div className="rm-form-row">
                    <label htmlFor="vs-name">{t("vsPolicyName")}</label>
                    <input
                      id="vs-name"
                      type="text"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="scan_all_cifs"
                      disabled={busy}
                    />
                  </div>
                  <div className="rm-form-row">
                    <label htmlFor="vs-max">{t("vsMaxFileSize")} (MB)</label>
                    <input
                      id="vs-max"
                      type="number"
                      min={1}
                      value={newMaxMb}
                      onChange={(e) => setNewMaxMb(Number(e.target.value))}
                      disabled={busy}
                    />
                  </div>
                  <div className="rm-form-row">
                    <label htmlFor="vs-ext">{t("vsExcludedExt")}</label>
                    <input
                      id="vs-ext"
                      type="text"
                      value={newExts}
                      onChange={(e) => setNewExts(e.target.value)}
                      placeholder="tmp, log"
                      disabled={busy}
                    />
                  </div>
                  <div className="rm-form-row">
                    <label htmlFor="vs-mandatory">{t("vsMandatory")}</label>
                    <input
                      id="vs-mandatory"
                      type="checkbox"
                      checked={newMandatory}
                      onChange={(e) => setNewMandatory(e.target.checked)}
                      disabled={busy}
                    />
                  </div>
                  <div className="rm-form-actions">
                    <button
                      className="rm-btn-primary"
                      disabled={busy || !newName.trim()}
                      onClick={createPolicy}
                    >
                      {t("rmCreate")}
                    </button>
                    <button className="rm-btn-secondary" onClick={() => setShowCreate(false)}>
                      {t("cancel")}
                    </button>
                  </div>
                  <p className="rm-hint">{t("vsCreateHint")}</p>
                </div>
              )}

              {policies.length === 0 ? (
                <p className="rm-empty">{t("vsNoPolicies")}</p>
              ) : (
                <table className="rm-table">
                  <thead>
                    <tr>
                      <th>{t("vsPolicyName")}</th>
                      <th>{t("fpEnabled")}</th>
                      <th>{t("vsMandatory")}</th>
                      <th>{t("vsMaxFileSize")}</th>
                      <th>{t("vsExcludedExt")}</th>
                      <th>{t("rmActions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {policies.map((p) => (
                      <tr key={p.name}>
                        <td className="lu-username">{p.name}</td>
                        <td>
                          <span className={`lu-badge ${p.enabled ? "active" : "disabled"}`}>
                            {p.enabled ? t("luActive") : t("luDisabled")}
                          </span>
                        </td>
                        <td>{p.mandatory ? "✅" : "—"}</td>
                        <td>
                          {p.maxFileSize > 0
                            ? `${Math.round(p.maxFileSize / (1024 * 1024))} MB`
                            : "—"}
                        </td>
                        <td>
                          {p.excludedExtensions.length > 0
                            ? p.excludedExtensions.join(", ")
                            : "—"}
                        </td>
                        <td>
                          <span className="sm-actions" style={{ padding: 0, border: "none" }}>
                            <button
                              className="rm-btn-sm"
                              disabled={busy}
                              onClick={() =>
                                runAction("setVscanPolicyEnabled", {
                                  name: p.name,
                                  enabled: !p.enabled,
                                })
                              }
                            >
                              {p.enabled ? t("vsDisableBtn") : t("vsEnableBtn")}
                            </button>
                            <button
                              className="rm-btn-danger-sm"
                              disabled={busy}
                              onClick={() => setConfirmFor(p.name)}
                            >
                              {t("delete")}
                            </button>
                          </span>
                          {confirmFor === p.name && (
                            <span className="peer-accept-row" role="alertdialog">
                              <span className="sm-confirm-text">
                                {t("vsConfirmDeletePolicy")}
                              </span>
                              <button
                                className="rm-btn-danger-sm"
                                disabled={busy}
                                onClick={() =>
                                  runAction("deleteVscanPolicy", {
                                    name: p.name,
                                    confirm: true,
                                  })
                                }
                              >
                                {t("rmExecute")}
                              </button>
                              <button
                                className="rm-btn-sm"
                                onClick={() => setConfirmFor(null)}
                              >
                                {t("cancel")}
                              </button>
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
