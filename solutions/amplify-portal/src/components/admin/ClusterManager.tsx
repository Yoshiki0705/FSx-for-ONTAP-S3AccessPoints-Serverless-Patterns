import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { adminMutate, adminQuery, type DispatchCall } from "../../lib/dispatch";
import type { ParamsOf } from "../../lib/dispatchActions";
import { errorMessage } from "../../lib/portalQuery";

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
  /**
   * Typed as the set the enable/disable action accepts, so a row can be handed
   * straight to it. The listing and that action are the same handler's two halves,
   * and it enumerates these three.
   */
  protocol: NonNullable<ParamsOf<"adminMutation", "setProtocolServiceEnabled">["protocol"]>;
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
  // The DNS inputs are an editable form seeded from the cluster. State holds
  // only what the operator typed; until then the loaded value is shown. Seeding
  // state from the response would need an effect and an extra render pass.
  const [dnsDraft, setDnsDraft] = useState<{ domains: string; servers: string } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmFor, setConfirmFor] = useState<string | null>(null);

  const isTransient = (msg?: string) =>
    !!msg && (msg.includes("Unknown action") || msg.includes("not configured"));



  // One query per tab. Each tab fetches only what it renders, and the tab is
  // part of the key so going back to a tab shows its data straight away.
  const {
    data,
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "cluster", tab],
    queryFn: async () => {
      // A dispatcher that is not wired yet leaves the section empty rather than
      // failing the whole tab.
      const fail = (msg?: string) => {
        if (msg && !isTransient(msg)) throw new Error(msg);
      };
      if (tab === "overview") {
        const info = await adminQuery<ClusterInfo>({ action: "getClusterInfo" });
        fail(info?.error);
        const n = await adminQuery<{ nodes?: NodeInfo[] }>({ action: "listNodes" });
        const l = await adminQuery<{ licenses?: LicenseInfo[] }>({ action: "listLicenses" });
        return {
          cluster: info ? { name: info.name, version: info.version } : null,
          nodes: n?.nodes ?? [],
          licenses: l?.licenses ?? [],
        };
      }
      if (tab === "interfaces") {
        const i = await adminQuery<{ interfaces?: InterfaceInfo[] }>({
          action: "listNetworkInterfaces",
        });
        fail(i?.error);
        return { interfaces: i?.interfaces ?? [] };
      }
      if (tab === "services") {
        const s = await adminQuery<{ services?: ServiceInfo[] }>({
          action: "listProtocolServices",
        });
        fail(s?.error);
        const d = await adminQuery<{ domains?: string[]; servers?: string[] }>({
          action: "getDnsConfig",
        });
        return {
          services: s?.services ?? [],
          dns: {
            domains: (d?.domains ?? []).join(", "),
            servers: (d?.servers ?? []).join(", "),
          },
        };
      }
      const j = await adminQuery<{ jobs?: JobInfo[] }>({ action: "listJobs" });
      fail(j?.error);
      return { jobs: j?.jobs ?? [] };
    },
  });

  const cluster = ("cluster" in (data ?? {}) ? data!.cluster : null) as ClusterInfo | null;
  const nodes = ("nodes" in (data ?? {}) ? data!.nodes : []) as NodeInfo[];
  const licenses = ("licenses" in (data ?? {}) ? data!.licenses : []) as LicenseInfo[];
  const interfaces = ("interfaces" in (data ?? {}) ? data!.interfaces : []) as InterfaceInfo[];
  const services = ("services" in (data ?? {}) ? data!.services : []) as ServiceInfo[];
  const jobs = ("jobs" in (data ?? {}) ? data!.jobs : []) as JobInfo[];
  const loadedDns = ("dns" in (data ?? {}) ? data!.dns : null) as
    | { domains: string; servers: string }
    | null;

  const dnsDomains = dnsDraft?.domains ?? loadedDns?.domains ?? "";
  const dnsServers = dnsDraft?.servers ?? loadedDns?.servers ?? "";
  const setDnsDomains = (v: string) => setDnsDraft({ domains: v, servers: dnsServers });
  const setDnsServers = (v: string) => setDnsDraft({ domains: dnsDomains, servers: v });

  // Mutation handlers report through their own state, so a failed action is
  // never mistaken for a failed load.
  const loadData = () => void refetch();
  const error = actionError ?? errorMessage(queryError, "Load failed");

  // Takes the whole call rather than an action name and a loose bag, so each
  // button's parameters are checked against the action it names.
  const runAction = async (call: DispatchCall<"adminMutation">) => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await adminMutate<{ success?: boolean }>(call);
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
            <>
              <p className="rm-empty">{t("clNoNodes")}</p>
              <p className="rm-hint">{t("clManagedByAwsHint")}</p>
            </>
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
            <>
              <p className="rm-empty">{t("clNoLicenses")}</p>
              <p className="rm-hint">{t("clManagedByAwsHint")}</p>
            </>
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
                                runAction({
                                  action: "setNetworkInterfaceEnabled",
                                  params: { uuid: i.uuid, enabled: false, confirm: true },
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
                            runAction({
                              action: "setNetworkInterfaceEnabled",
                              params: { uuid: i.uuid, enabled: true },
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
                                runAction({
                                  action: "setProtocolServiceEnabled",
                                  params: { protocol: s.protocol, enabled: false, confirm: true },
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
                            runAction({
                              action: "setProtocolServiceEnabled",
                              params: { protocol: s.protocol, enabled: true },
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
                  runAction({
                    action: "updateDnsConfig",
                    params: {
                      domains: dnsDomains.split(",").map((s) => s.trim()).filter(Boolean),
                      servers: dnsServers.split(",").map((s) => s.trim()).filter(Boolean),
                    },
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
