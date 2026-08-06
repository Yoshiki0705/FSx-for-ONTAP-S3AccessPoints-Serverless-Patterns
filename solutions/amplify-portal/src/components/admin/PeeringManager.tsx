import { useState, useEffect, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";
import { parseResponse } from "../../utils/parseResponse";

const client = generateClient<Schema>();

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
  const [lifs, setLifs] = useState<InterclusterLif[]>([]);
  const [clusterPeers, setClusterPeers] = useState<ClusterPeer[]>([]);
  const [svmPeers, setSvmPeers] = useState<SvmPeer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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

  const isTransient = (msg?: string) =>
    !!msg && (msg.includes("Unknown action") || msg.includes("not configured"));

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const action =
        tab === "cluster" ? "listClusterPeers" : tab === "svm" ? "listSvmPeers" : "listInterclusterLifs";
      const resp = await client.queries.adminQuery({
        action,
        params: JSON.stringify({}),
      });
      if (tab === "cluster") {
        const data = parseResponse<{ peers?: ClusterPeer[]; error?: string }>(resp);
        if (data?.error && !isTransient(data.error)) setError(data.error);
        else setClusterPeers(data?.peers || []);
      } else if (tab === "svm") {
        const data = parseResponse<{ peers?: SvmPeer[]; error?: string }>(resp);
        if (data?.error && !isTransient(data.error)) setError(data.error);
        else setSvmPeers(data?.peers || []);
      } else {
        const data = parseResponse<{ lifs?: InterclusterLif[]; error?: string }>(resp);
        if (data?.error && !isTransient(data.error)) setError(data.error);
        else setLifs(data?.lifs || []);
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
      const resp = await client.mutations.adminMutation({
        action,
        params: JSON.stringify(params),
      });
      const data = parseResponse<{ success?: boolean; error?: string; passphrase?: string }>(resp);
      if (data?.success) {
        if (data.passphrase) setGeneratedPassphrase(data.passphrase);
        setSuccess(t("peerActionDone"));
        setTimeout(() => setSuccess(null), 5000);
        setShowCreateCluster(false);
        setShowCreateSvm(false);
        setAcceptFor(null);
        setConfirmFor(null);
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
              🔄 {t("rmApply")}
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
                    runAction("createClusterPeer", {
                      remoteAddresses: remoteAddrs
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                      generatePassphrase: useGenerated,
                      passphrase: useGenerated ? undefined : passphrase,
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
                              runAction("acceptClusterPeer", {
                                uuid: p.uuid,
                                passphrase: acceptPassphrase,
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
                            onClick={() => runAction("deleteClusterPeer", { uuid: p.uuid, confirm: true })}
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
                    runAction("createSvmPeer", {
                      peerSvm: peerSvm.trim(),
                      peerCluster: peerCluster.trim() || undefined,
                      applications: ["snapmirror"],
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
                            onClick={() => runAction("acceptSvmPeer", { uuid: p.uuid })}
                          >
                            {t("peerAccept")}
                          </button>
                        )}
                        <button
                          className="rm-btn-danger-sm"
                          disabled={busy}
                          onClick={() => runAction("deleteSvmPeer", { uuid: p.uuid, confirm: true })}
                        >
                          {t("delete")}
                        </button>
                      </span>
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
