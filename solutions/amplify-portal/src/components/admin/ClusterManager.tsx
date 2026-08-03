import { useState, useEffect, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";

const client = generateClient<Schema>();

function parseResponse<T>(response: { data?: string | null }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === "string" ? JSON.parse(response.data) : response.data;
  } catch {
    return null;
  }
}

interface ClusterInfo {
  name: string;
  version: string;
}

interface NodeInfo {
  name: string;
  uuid: string;
  state: string;
  model: string;
  serialNumber: string;
  version: string;
  uptimeSeconds: number;
  haEnabled: boolean;
  haPartners: string[];
}

interface LicenseInfo {
  name: string;
  state: string;
  scope: string;
  expiryTime: string;
}

interface InterfaceInfo {
  name: string;
  uuid: string;
  address: string;
  enabled: boolean;
  state: string;
  scope: string;
  svmName: string;
  node: string;
  port: string;
  services: string[];
}

interface ServiceInfo {
  protocol: string;
  enabled: boolean;
  state: string;
  detail: string;
}

interface JobInfo {
  uuid: string;
  description: string;
  state: string;
  message: string;
  startTime: string;
  endTime: string;
}

type Tab = "overview" | "interfaces" | "services" | "jobs";

/**
 * Cluster inventory and services.
 *
 * Covers the cluster-level information that the AWS console does not surface:
 * node health and HA pairing, licence state, LIF inventory, which data protocols
 * are running, DNS resolvers, and the asynchronous job queue that FlexCache,
 * FlexClone, SnapMirror and peering operations report into.
 */
export function ClusterManager() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("overview");
  const [cluster, setCluster] = useState<ClusterInfo | null>(null);
  const [nodes, setNodes] = useState<NodeInfo[]>([]);
  const [licenses, setLicenses] = useState<LicenseInfo[]>([]);
  const [interfaces, setInterfaces] = useState<InterfaceInfo[]>([]);
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [jobs, setJobs] = useState<JobInfo[]>([]);
  const [dnsDomains, setDnsDomains] = useState("");
  const [dnsServers, setDnsServers] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmFor, setConfirmFor] = useState<string | null>(null);

  const isTransient = (msg?: string) =>
    !!msg && (msg.includes("Unknown action") || msg.includes("not configured"));

  const query = async <T,>(action: string, params: Record<string, unknown> = {}) => {
    const resp = await (client.queries as any).adminQuery({
      action,
      params: JSON.stringify(params),
    });
    return parseResponse<T & { error?: string }>(resp);
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (tab === "overview") {
        const info = await query<ClusterInfo>("getClusterInfo");
        if (info?.error && !isTransient(info.error)) setError(info.error);
        else if (info) setCluster({ name: info.name, version: info.version });

        const n = await query<{ nodes?: NodeInfo[] }>("listNodes");
        setNodes(n?.nodes || []);
        const l = await query<{ licenses?: LicenseInfo[] }>("listLicenses");
        setLicenses(l?.licenses || []);
      } else if (tab === "interfaces") {
        const i = await query<{ interfaces?: InterfaceInfo[] }>("listNetworkInterfaces");
        if (i?.error && !isTransient(i.error)) setError(i.error);
        else setInterfaces(i?.interfaces || []);
      } else if (tab === "services") {
        const s = await query<{ services?: ServiceInfo[] }>("listProtocolServices");
        if (s?.error && !isTransient(s.error)) setError(s.error);
        else setServices(s?.services || []);
        const d = await query<{ domains?: string[]; servers?: string[] }>("getDnsConfig");
        setDnsDomains((d?.domains || []).join(", "));
        setDnsServers((d?.servers || []).join(", "));
      } else {
        const j = await query<{ jobs?: JobInfo[] }>("listJobs");
        if (j?.error && !isTransient(j.error)) setError(j.error);
        else setJobs(j?.jobs || []);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    loadData();
  }, [loadData]);

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
        setSuccess(t("clActionDone"));
        setTimeout(() => setSuccess(null), 4000);
        setConfirmFor(null);
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

  const formatUptime = (seconds: number) => {
    if (!seconds) return "—";
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    return d > 0 ? `${d}d ${h}h` : `${h}h`;
  };

  return (
    <div className="cluster-manager">
      <div className="lu-tabs">
        <button className={`lu-tab ${tab === "overview" ? "active" : ""}`} onClick={() => setTab("overview")}>
          🖥️ {t("clOverviewTab")}
        </button>
        <button
          className={`lu-tab ${tab === "interfaces" ? "active" : ""}`}
          onClick={() => setTab("interfaces")}
        >
          🌐 {t("clInterfacesTab")}
        </button>
        <button className={`lu-tab ${tab === "services" ? "active" : ""}`} onClick={() => setTab("services")}>
          ⚙️ {t("clServicesTab")}
        </button>
        <button className={`lu-tab ${tab === "jobs" ? "active" : ""}`} onClick={() => setTab("jobs")}>
          📜 {t("clJobsTab")}
        </button>
      </div>

      {error && <div className="rm-error">⚠️ {error}</div>}
      {success && <div className="rm-success">✅ {success}</div>}

      {loading ? (
        <div className="rm-loading">{t("ontapConnecting")}</div>
      ) : tab === "overview" ? (
        <>
          <div className="lu-toolbar">
            <span className="lu-count">
              {cluster?.name || "—"}{" "}
              {cluster?.version && <span className="lu-group-desc">{cluster.version}</span>}
            </span>
            <button className="rm-btn-sm" onClick={loadData}>
              🔄 {t("rmApply")}
            </button>
          </div>

          <h4>{t("clNodes")}</h4>
          {nodes.length === 0 ? (
            <p className="rm-empty">{t("clNoNodes")}</p>
          ) : (
            <table className="rm-table">
              <thead>
                <tr>
                  <th>{t("clNodeName")}</th>
                  <th>{t("rmState")}</th>
                  <th>{t("clUptime")}</th>
                  <th>{t("clHa")}</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((n) => (
                  <tr key={n.uuid}>
                    <td className="lu-username">{n.name}</td>
                    <td>
                      <span className={`lu-badge ${n.state === "up" ? "active" : "disabled"}`}>{n.state}</span>
                    </td>
                    <td>{formatUptime(n.uptimeSeconds)}</td>
                    <td>{n.haEnabled ? n.haPartners.join(", ") || "✅" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h4 style={{ marginTop: "1rem" }}>{t("clLicenses")}</h4>
          {licenses.length === 0 ? (
            <p className="rm-empty">{t("clNoLicenses")}</p>
          ) : (
            <table className="rm-table">
              <thead>
                <tr>
                  <th>{t("clLicenseName")}</th>
                  <th>{t("rmState")}</th>
                  <th>{t("clScope")}</th>
                </tr>
              </thead>
              <tbody>
                {licenses.map((l) => (
                  <tr key={l.name}>
                    <td className="lu-username">{l.name}</td>
                    <td>
                      <span className={`lu-badge ${l.state === "compliant" ? "active" : "disabled"}`}>
                        {l.state}
                      </span>
                    </td>
                    <td>{l.scope}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : tab === "interfaces" ? (
        <>
          <div className="lu-toolbar">
            <span className="lu-count">
              {interfaces.length} {t("clInterfacesTab")}
            </span>
            <button className="rm-btn-sm" onClick={loadData}>
              🔄 {t("rmApply")}
            </button>
          </div>
          {interfaces.length === 0 ? (
            <p className="rm-empty">{t("clNoInterfaces")}</p>
          ) : (
            <table className="rm-table">
              <thead>
                <tr>
                  <th>{t("peerLifName")}</th>
                  <th>{t("peerAddress")}</th>
                  <th>{t("rmState")}</th>
                  <th>SVM</th>
                  <th>{t("clServices")}</th>
                  <th>{t("rmActions")}</th>
                </tr>
              </thead>
              <tbody>
                {interfaces.map((i) => (
                  <tr key={i.uuid}>
                    <td className="lu-username">{i.name}</td>
                    <td>{i.address}</td>
                    <td>
                      <span className={`lu-badge ${i.enabled && i.state === "up" ? "active" : "disabled"}`}>
                        {i.state || (i.enabled ? "up" : "down")}
                      </span>
                    </td>
                    <td>{i.svmName || "—"}</td>
                    <td className="cl-services">{i.services.join(", ") || "—"}</td>
                    <td>
                      {i.enabled ? (
                        confirmFor === i.uuid ? (
                          <span className="peer-accept-row">
                            <span className="sm-confirm-text">{t("clConfirmDisableLif")}</span>
                            <button
                              className="rm-btn-danger-sm"
                              disabled={busy}
                              onClick={() =>
                                runAction("setNetworkInterfaceEnabled", {
                                  uuid: i.uuid,
                                  enabled: false,
                                  confirm: true,
                                })
                              }
                            >
                              {t("rmExecute")}
                            </button>
                            <button className="rm-btn-sm" onClick={() => setConfirmFor(null)}>
                              {t("cancel")}
                            </button>
                          </span>
                        ) : (
                          <button
                            className="rm-btn-danger-sm"
                            disabled={busy}
                            onClick={() => setConfirmFor(i.uuid)}
                          >
                            {t("clDisable")}
                          </button>
                        )
                      ) : (
                        <button
                          className="rm-btn-sm"
                          disabled={busy}
                          onClick={() =>
                            runAction("setNetworkInterfaceEnabled", { uuid: i.uuid, enabled: true })
                          }
                        >
                          {t("clEnable")}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : tab === "services" ? (
        <>
          <h4>{t("clProtocols")}</h4>
          {services.length === 0 ? (
            <p className="rm-empty">{t("clNoServices")}</p>
          ) : (
            <table className="rm-table">
              <thead>
                <tr>
                  <th>{t("clProtocol")}</th>
                  <th>{t("rmState")}</th>
                  <th>{t("clDetail")}</th>
                  <th>{t("rmActions")}</th>
                </tr>
              </thead>
              <tbody>
                {services.map((s) => (
                  <tr key={s.protocol}>
                    <td className="lu-username">{s.protocol.toUpperCase()}</td>
                    <td>
                      <span className={`lu-badge ${s.enabled ? "active" : "disabled"}`}>
                        {s.enabled ? t("luActive") : t("luDisabled")}
                      </span>
                    </td>
                    <td>{s.detail || "—"}</td>
                    <td>
                      {s.enabled ? (
                        confirmFor === s.protocol ? (
                          <span className="peer-accept-row">
                            <span className="sm-confirm-text">{t("clConfirmDisableProtocol")}</span>
                            <button
                              className="rm-btn-danger-sm"
                              disabled={busy}
                              onClick={() =>
                                runAction("setProtocolServiceEnabled", {
                                  protocol: s.protocol,
                                  enabled: false,
                                  confirm: true,
                                })
                              }
                            >
                              {t("rmExecute")}
                            </button>
                            <button className="rm-btn-sm" onClick={() => setConfirmFor(null)}>
                              {t("cancel")}
                            </button>
                          </span>
                        ) : (
                          <button
                            className="rm-btn-danger-sm"
                            disabled={busy}
                            onClick={() => setConfirmFor(s.protocol)}
                          >
                            {t("clDisable")}
                          </button>
                        )
                      ) : (
                        <button
                          className="rm-btn-sm"
                          disabled={busy}
                          onClick={() =>
                            runAction("setProtocolServiceEnabled", {
                              protocol: s.protocol,
                              enabled: true,
                            })
                          }
                        >
                          {t("clEnable")}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h4 style={{ marginTop: "1rem" }}>{t("clDns")}</h4>
          <div className="rm-form">
            <div className="rm-form-row">
              <label htmlFor="cl-dns-domains">{t("clDnsDomains")}</label>
              <input
                id="cl-dns-domains"
                type="text"
                value={dnsDomains}
                onChange={(e) => setDnsDomains(e.target.value)}
                placeholder="demo.fsx.local"
                disabled={busy}
              />
            </div>
            <div className="rm-form-row">
              <label htmlFor="cl-dns-servers">{t("clDnsServers")}</label>
              <input
                id="cl-dns-servers"
                type="text"
                value={dnsServers}
                onChange={(e) => setDnsServers(e.target.value)}
                placeholder="198.51.100.10, 198.51.100.11"
                disabled={busy}
              />
            </div>
            <div className="rm-form-actions">
              <button
                className="rm-btn-primary"
                disabled={busy || !dnsDomains.trim() || !dnsServers.trim()}
                onClick={() =>
                  runAction("updateDnsConfig", {
                    domains: dnsDomains.split(",").map((s) => s.trim()).filter(Boolean),
                    servers: dnsServers.split(",").map((s) => s.trim()).filter(Boolean),
                  })
                }
              >
                {t("rmApply")}
              </button>
            </div>
            <p className="rm-hint">{t("clDnsHint")}</p>
          </div>
        </>
      ) : (
        <>
          <div className="lu-toolbar">
            <span className="lu-count">
              {jobs.length} {t("clJobsTab")}
            </span>
            <button className="rm-btn-sm" onClick={loadData}>
              🔄 {t("rmApply")}
            </button>
          </div>
          <p className="rm-hint">{t("clJobsHint")}</p>
          {jobs.length === 0 ? (
            <p className="rm-empty">{t("clNoJobs")}</p>
          ) : (
            <table className="rm-table">
              <thead>
                <tr>
                  <th>{t("clJobDescription")}</th>
                  <th>{t("rmState")}</th>
                  <th>{t("clJobMessage")}</th>
                  <th>{t("smEndTime")}</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.uuid}>
                    <td>{j.description || "—"}</td>
                    <td>
                      <span
                        className={`lu-badge ${
                          j.state === "success" ? "active" : j.state === "failure" ? "disabled" : ""
                        }`}
                      >
                        {j.state}
                      </span>
                    </td>
                    <td>{j.message || "—"}</td>
                    <td>{j.endTime ? new Date(j.endTime).toLocaleString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
