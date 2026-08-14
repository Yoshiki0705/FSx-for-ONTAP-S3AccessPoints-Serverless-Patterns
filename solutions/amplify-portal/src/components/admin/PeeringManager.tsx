import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage } from "../../lib/portalQuery";
import { adminMutate, adminQuery, type DispatchCall } from "../../lib/dispatch";

interface InterclusterLif {
  name: string;
  uuid: string;
  address: string;
  enabled: boolean;
  state: string;
  node: string;
}

interface ClusterPeer {
  name: string;
  uuid: string;
  state: string;
  updateTime: string;
  remoteName: string;
  remoteAddresses: string[];
  authState: string;
  encryptionState: string;
  ipspace: string;
}

interface SvmPeer {
  name: string;
  uuid: string;
  state: string;
  applications: string[];
  localSvm: string;
  peerSvm: string;
  peerCluster: string;
}

type Tab = "cluster" | "svm" | "lifs";

/**
 * Cluster and SVM peering.
 *
 * Peering is a prerequisite for cross-cluster replication and FlexCache, and it
 * is not available in the AWS console, so it normally has to be done through the
 * ONTAP CLI or REST API by hand. This panel covers the whole flow: checking the
 * intercluster LIFs, creating the relationship, exchanging the passphrase, and
 * accepting it on the other side.
 */
export function PeeringManager() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("cluster");
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmFor, setConfirmFor] = useState<string | null>(null);

  // Passphrase returned by ONTAP on creation; shown once so it can be carried
  // to the remote cluster.
  const [generatedPassphrase, setGeneratedPassphrase] = useState<string | null>(null);

  const [showCreateCluster, setShowCreateCluster] = useState(false);
  const [remoteAddrs, setRemoteAddrs] = useState("");
  const [useGenerated, setUseGenerated] = useState(true);
  const [passphrase, setPassphrase] = useState("");

  const [showCreateSvm, setShowCreateSvm] = useState(false);
  const [peerSvm, setPeerSvm] = useState("");
  const [peerCluster, setPeerCluster] = useState("");

  const [acceptFor, setAcceptFor] = useState<string | null>(null);
  const [acceptPassphrase, setAcceptPassphrase] = useState("");

  // Which peer's uses are being edited, and the set being edited. A peer created
  // for FlexCache is `peered` and still refuses SnapMirror, which reads from the
  // replication side as "not peered" and sends people to the cluster peer instead.
  const [appsFor, setAppsFor] = useState<string | null>(null);
  const [editApps, setEditApps] = useState<string[]>([]);

  const toggleApp = (app: string) =>
    setEditApps(prev => (prev.includes(app) ? prev.filter(a => a !== app) : [...prev, app]));

  const isTransient = (msg?: string) =>
    !!msg && (msg.includes("Unknown action") || msg.includes("not configured"));

  // One query per tab. The tab is part of the key, so switching tabs serves the
  // cached list immediately instead of refetching from scratch.
  const {
    data: peering,
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "peering", tab],
    queryFn: async () => {
      // Written out per branch: a computed action name is unreadable to the
      // parameter check and bypasses the per-action parameter type.
      const call =
        tab === "cluster"
          ? ({ action: "listClusterPeers" } as const)
          : tab === "svm"
            ? ({ action: "listSvmPeers" } as const)
            : ({ action: "listInterclusterLifs" } as const);
      const data = await adminQuery<{
        peers?: ClusterPeer[] | SvmPeer[];
        lifs?: InterclusterLif[];
      }>(call);
      // A dispatcher that is not wired yet is an empty list, not a failure.
      if (data?.error && !isTransient(data.error)) throw new Error(data.error);
      return data;
    },
  });

  const clusterPeers = (tab === "cluster" ? peering?.peers ?? [] : []) as ClusterPeer[];
  const svmPeers = (tab === "svm" ? peering?.peers ?? [] : []) as SvmPeer[];
  const lifs = tab === "lifs" ? peering?.lifs ?? [] : [];

  // Mutation handlers report through their own state, so a failed action is
  // never mistaken for a failed load.
  const loadData = () => void refetch();
  const error = actionError ?? errorMessage(queryError, "Failed to load peering");

  // Takes the whole call rather than an action name and a loose bag, so each
  // button's parameters are checked against the action it names.
  const runAction = async (call: DispatchCall<"adminMutation">) => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await adminMutate<{ success?: boolean; passphrase?: string }>(call);
      if (data?.success) {
        if (data.passphrase) setGeneratedPassphrase(data.passphrase);
        setSuccess(t("peerActionDone"));
        setTimeout(() => setSuccess(null), 5000);
        setShowCreateCluster(false);
        setShowCreateSvm(false);
        setAcceptFor(null);
        setConfirmFor(null);
        setAppsFor(null);
        setAcceptPassphrase("");
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

  const healthyLifs = lifs.filter((l) => l.enabled && l.state === "up").length;

  return (
    <div className="peering-manager">
      <div className="lu-tabs">
        <button className={`lu-tab ${tab === "cluster" ? "active" : ""}`} onClick={() => setTab("cluster")}>
          🔗 {t("peerClusterTab")}
        </button>
        <button className={`lu-tab ${tab === "svm" ? "active" : ""}`} onClick={() => setTab("svm")}>
          🗂️ {t("peerSvmTab")}
        </button>
        <button className={`lu-tab ${tab === "lifs" ? "active" : ""}`} onClick={() => setTab("lifs")}>
          🌐 {t("peerLifTab")}
        </button>
      </div>

      {error && <div className="rm-error">⚠️ {error}</div>}
      {success && <div className="rm-success">✅ {success}</div>}

      {generatedPassphrase && (
        <div className="peer-passphrase" role="status">
          <strong>{t("peerPassphraseTitle")}</strong>
          <code className="peer-passphrase-value">{generatedPassphrase}</code>
          <p className="rm-hint">{t("peerPassphraseHint")}</p>
          <button className="rm-btn-sm" onClick={() => setGeneratedPassphrase(null)}>
            {t("peerPassphraseDismiss")}
          </button>
        </div>
      )}

      {loading ? (
        <div className="rm-loading">{t("ontapConnecting")}</div>
      ) : tab === "lifs" ? (
        <>
          <div className="lu-toolbar">
            <span className="lu-count">
              {lifs.length} {t("peerLifTab")}
            </span>
            <span className={`lu-badge ${healthyLifs > 0 ? "active" : "disabled"}`}>
              {healthyLifs > 0 ? t("peerLifReady") : t("peerLifMissing")}
            </span>
            <button className="rm-btn-sm" onClick={loadData}>
              🔄 {t("refresh")}
            </button>
          </div>
          <p className="rm-hint">{t("peerLifHint")}</p>
          {lifs.length === 0 ? (
            <p className="rm-empty">{t("peerNoLifs")}</p>
          ) : (
            <table className="rm-table">
              <thead>
                <tr>
                  <th>{t("peerLifName")}</th>
                  <th>{t("peerAddress")}</th>
                  <th>{t("rmState")}</th>
                  <th>Node</th>
                </tr>
              </thead>
              <tbody>
                {lifs.map((l) => (
                  <tr key={l.uuid}>
                    <td className="lu-username">{l.name}</td>
                    <td>{l.address}</td>
                    <td>
                      <span className={`lu-badge ${l.enabled && l.state === "up" ? "active" : "disabled"}`}>
                        {l.state || (l.enabled ? "up" : "down")}
                      </span>
                    </td>
                    <td>{l.node}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : tab === "cluster" ? (
        <>
          <div className="lu-toolbar">
            <span className="lu-count">
              {clusterPeers.length} {t("peerClusterTab")}
            </span>
            <button className="rm-btn-primary" disabled={busy} onClick={() => setShowCreateCluster((v) => !v)}>
              + {t("peerCreateCluster")}
            </button>
          </div>

          {showCreateCluster && (
            <div className="rm-form">
              <h4>{t("peerCreateCluster")}</h4>
              <div className="rm-form-row">
                <label htmlFor="peer-addrs">{t("peerRemoteAddresses")}</label>
                <input
                  id="peer-addrs"
                  type="text"
                  value={remoteAddrs}
                  onChange={(e) => setRemoteAddrs(e.target.value)}
                  placeholder="198.51.100.10, 198.51.100.11"
                  disabled={busy}
                />
              </div>
              <div className="rm-form-row">
                <label htmlFor="peer-gen">{t("peerGeneratePassphrase")}</label>
                <input
                  id="peer-gen"
                  type="checkbox"
                  checked={useGenerated}
                  onChange={(e) => setUseGenerated(e.target.checked)}
                  disabled={busy}
                />
              </div>
              {!useGenerated && (
                <div className="rm-form-row">
                  <label htmlFor="peer-pass">{t("peerPassphrase")}</label>
                  <input
                    id="peer-pass"
                    type="password"
                    value={passphrase}
                    onChange={(e) => setPassphrase(e.target.value)}
                    disabled={busy}
                  />
                </div>
              )}
              <div className="rm-form-actions">
                <button
                  className="rm-btn-primary"
                  disabled={busy || !remoteAddrs.trim() || (!useGenerated && !passphrase)}
                  onClick={() =>
                    runAction({
                      action: "createClusterPeer",
                      params: {
                        remoteAddresses: remoteAddrs
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean),
                        generatePassphrase: useGenerated,
                        passphrase: useGenerated ? undefined : passphrase,
                      },
                    })
                  }
                >
                  {t("rmCreate")}
                </button>
                <button className="rm-btn-secondary" onClick={() => setShowCreateCluster(false)}>
                  {t("cancel")}
                </button>
              </div>
              <p className="rm-hint">{t("peerCreateClusterHint")}</p>
            </div>
          )}

          {clusterPeers.length === 0 ? (
            <p className="rm-empty">{t("peerNoClusterPeers")}</p>
          ) : (
            <table className="rm-table">
              <thead>
                <tr>
                  <th>{t("peerName")}</th>
                  <th>{t("rmState")}</th>
                  <th>{t("peerAuth")}</th>
                  <th>{t("peerAddress")}</th>
                  <th>{t("rmActions")}</th>
                </tr>
              </thead>
              <tbody>
                {clusterPeers.map((p) => (
                  <tr key={p.uuid}>
                    <td className="lu-username">{p.remoteName || p.name}</td>
                    <td>
                      <span className={`lu-badge ${p.state === "available" ? "active" : "disabled"}`}>
                        {p.state}
                      </span>
                    </td>
                    <td>{p.authState || "—"}</td>
                    <td>{p.remoteAddresses.join(", ") || "—"}</td>
                    <td>
                      <span className="sm-actions" style={{ padding: 0, border: "none" }}>
                        <button className="rm-btn-sm" disabled={busy} onClick={() => setAcceptFor(p.uuid)}>
                          {t("peerAccept")}
                        </button>
                        <button
                          className="rm-btn-danger-sm"
                          disabled={busy}
                          onClick={() => setConfirmFor(p.uuid)}
                        >
                          {t("delete")}
                        </button>
                      </span>
                      {acceptFor === p.uuid && (
                        <span className="peer-accept-row">
                          <input
                            type="password"
                            value={acceptPassphrase}
                            onChange={(e) => setAcceptPassphrase(e.target.value)}
                            placeholder={t("peerPassphrase")}
                            aria-label={t("peerPassphrase")}
                          />
                          <button
                            className="rm-btn-primary"
                            disabled={busy || !acceptPassphrase}
                            onClick={() =>
                              runAction({
                                action: "acceptClusterPeer",
                                params: { uuid: p.uuid, passphrase: acceptPassphrase },
                              })
                            }
                          >
                            {t("rmExecute")}
                          </button>
                          <button className="rm-btn-sm" onClick={() => setAcceptFor(null)}>
                            {t("cancel")}
                          </button>
                        </span>
                      )}
                      {confirmFor === p.uuid && (
                        <span className="peer-accept-row">
                          <span className="sm-confirm-text">{t("peerConfirmDeleteCluster")}</span>
                          <button
                            className="rm-btn-danger-sm"
                            disabled={busy}
                            onClick={() =>
                              runAction({
                                action: "deleteClusterPeer",
                                params: { uuid: p.uuid, confirm: true },
                              })
                            }
                          >
                            {t("rmExecute")}
                          </button>
                          <button className="rm-btn-sm" onClick={() => setConfirmFor(null)}>
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
      ) : (
        <>
          <div className="lu-toolbar">
            <span className="lu-count">
              {svmPeers.length} {t("peerSvmTab")}
            </span>
            <button className="rm-btn-primary" disabled={busy} onClick={() => setShowCreateSvm((v) => !v)}>
              + {t("peerCreateSvm")}
            </button>
          </div>
          <p className="rm-hint">{t("peerApplicationsHint")}</p>

          {showCreateSvm && (
            <div className="rm-form">
              <h4>{t("peerCreateSvm")}</h4>
              <div className="rm-form-row">
                <label htmlFor="peer-svm">{t("peerPeerSvm")}</label>
                <input
                  id="peer-svm"
                  type="text"
                  value={peerSvm}
                  onChange={(e) => setPeerSvm(e.target.value)}
                  placeholder="svm_dr"
                  disabled={busy}
                />
              </div>
              <div className="rm-form-row">
                <label htmlFor="peer-cluster">{t("peerPeerCluster")}</label>
                <input
                  id="peer-cluster"
                  type="text"
                  value={peerCluster}
                  onChange={(e) => setPeerCluster(e.target.value)}
                  placeholder="FsxId0123456789abcdef0"
                  disabled={busy}
                />
              </div>
              <div className="rm-form-actions">
                <button
                  className="rm-btn-primary"
                  disabled={busy || !peerSvm.trim()}
                  onClick={() =>
                    runAction({
                      action: "createSvmPeer",
                      params: {
                        peerSvm: peerSvm.trim(),
                        peerCluster: peerCluster.trim() || undefined,
                        applications: ["snapmirror"],
                      },
                    })
                  }
                >
                  {t("rmCreate")}
                </button>
                <button className="rm-btn-secondary" onClick={() => setShowCreateSvm(false)}>
                  {t("cancel")}
                </button>
              </div>
              <p className="rm-hint">{t("peerCreateSvmHint")}</p>
            </div>
          )}

          {svmPeers.length === 0 ? (
            <p className="rm-empty">{t("peerNoSvmPeers")}</p>
          ) : (
            <table className="rm-table">
              <thead>
                <tr>
                  <th>{t("peerLocalSvm")}</th>
                  <th>{t("peerPeerSvm")}</th>
                  <th>{t("peerPeerCluster")}</th>
                  <th>{t("rmState")}</th>
                  <th>{t("peerApplications")}</th>
                  <th>{t("rmActions")}</th>
                </tr>
              </thead>
              <tbody>
                {svmPeers.map((p) => (
                  <tr key={p.uuid}>
                    <td className="lu-username">{p.localSvm}</td>
                    <td>{p.peerSvm}</td>
                    <td>{p.peerCluster || "—"}</td>
                    <td>
                      <span className={`lu-badge ${p.state === "peered" ? "active" : "disabled"}`}>
                        {p.state}
                      </span>
                    </td>
                    <td>{p.applications.join(", ") || "—"}</td>
                    <td>
                      <span className="sm-actions" style={{ padding: 0, border: "none" }}>
                        {p.state !== "peered" && (
                          <button
                            className="rm-btn-sm"
                            disabled={busy}
                            onClick={() => runAction({ action: "acceptSvmPeer", params: { uuid: p.uuid } })}
                          >
                            {t("peerAccept")}
                          </button>
                        )}
                        <button
                          className="rm-btn-sm"
                          disabled={busy}
                          onClick={() => {
                            setAppsFor(p.uuid);
                            setEditApps(p.applications);
                          }}
                        >
                          {t("peerEditApplications")}
                        </button>
                        <button
                          className="rm-btn-danger-sm"
                          disabled={busy}
                          onClick={() =>
                            runAction({ action: "deleteSvmPeer", params: { uuid: p.uuid, confirm: true } })
                          }
                        >
                          {t("delete")}
                        </button>
                      </span>
                      {appsFor === p.uuid && (
                        <span className="peer-accept-row">
                          {["snapmirror", "flexcache"].map(app => (
                            <label key={app} className="peer-app-toggle">
                              <input
                                type="checkbox"
                                checked={editApps.includes(app)}
                                onChange={() => toggleApp(app)}
                                disabled={busy}
                              />
                              {app}
                            </label>
                          ))}
                          <button
                            className="rm-btn-primary"
                            disabled={busy || editApps.length === 0}
                            onClick={() =>
                              runAction({
                                action: "updateSvmPeerApplications",
                                params: { peerUuid: p.uuid, applications: editApps },
                              })
                            }
                          >
                            {t("rmApply")}
                          </button>
                          <button className="rm-btn-sm" onClick={() => setAppsFor(null)}>
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
    </div>
  );
}
