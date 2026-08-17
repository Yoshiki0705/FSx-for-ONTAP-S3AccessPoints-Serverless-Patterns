import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage, unwrap } from "../../lib/portalQuery";
import { adminMutate, dispatch } from "../../lib/dispatch";
import type { VolumeUuid } from "../../lib/dispatchActions";
import { copyText } from "../../utils/clipboard";

interface Lif {
  name: string;
  address: string;
  /** Enabled and up. A LIF that is neither serves nothing. */
  usable: boolean;
}

interface Share {
  name: string;
  path: string;
  encryption: boolean;
}

interface MountInfo {
  volumeName: string;
  svm: string;
  state: string;
  junctionPath: string;
  mounted: boolean;
  /** What the backend proposes for an unmounted volume: `/<name>`. */
  suggestedPath: string;
  nfsLifs: Lif[];
  smbLifs: Lif[];
  nfsEnabled: boolean;
  cifsEnabled: boolean;
  cifsServerName: string;
  cifsDomain: string;
  shares: Share[];
  /** Whether a command can be offered at all, rather than one that would time out. */
  nfsReady: boolean;
  smbReady: boolean;
  lifError: string;
}

/** The first LIF that can actually serve, or undefined when none can. */
function firstUsable(lifs: Lif[]): Lif | undefined {
  return lifs.find((lif) => lif.usable);
}

/**
 * The NFS mount command for this volume.
 *
 * Not translated: it is shell, and the same rule the failure notice states applies
 * here. `nfsvers=4.1` because that is what the FSx documentation uses and what the
 * rest of this repository's guides use, so an operator comparing the two sees one
 * command rather than two that differ in a way they have to think about.
 */
function nfsCommand(info: MountInfo, lif: Lif): string {
  const target = `${lif.address}:${info.junctionPath}`;
  const mountpoint = `/mnt/${info.volumeName || "fsxn"}`;
  return [`sudo mkdir -p ${mountpoint}`, `sudo mount -t nfs -o nfsvers=4.1 ${target} ${mountpoint}`].join("\n");
}

/**
 * The UNC path for a share, by name and by FQDN.
 *
 * Both are given because they fail in different places. `\\SERVER\share` resolves
 * only for a client whose DNS suffix already matches the SVM's domain; the FQDN
 * works from outside it. Showing one leaves the operator guessing which case they
 * are in when it does not resolve.
 */
function uncPaths(info: MountInfo, share: Share): string[] {
  const paths = [];
  if (info.cifsServerName) {
    paths.push(`\\\\${info.cifsServerName}\\${share.name}`);
    if (info.cifsDomain) {
      paths.push(`\\\\${info.cifsServerName}.${info.cifsDomain}\\${share.name}`);
    }
  }
  const lif = firstUsable(info.smbLifs);
  if (lif) paths.push(`\\\\${lif.address}\\${share.name}`);
  return paths;
}

/**
 * Mount management for one volume: the junction path, and how a client reaches it.
 *
 * Two things live here because they are the same question asked from both ends. The
 * junction path is what ONTAP needs; the mount command is what the operator on the
 * client needs. The AWS console pairs them the same way, and separating them left
 * the portal able to create a volume nobody could reach.
 *
 * Mounting is also the missing half of a repair. A delete unmounts before it offlines,
 * and a delete ONTAP refuses — a SnapLock volume holding an unexpired WORM file, or a
 * volume with a clone — leaves the volume online and unmounted. `bringVolumeOnline`
 * reverses the offline step; this reverses the other one.
 */
export function VolumeMountPanel({
  volumeUuid,
  volumeName,
  onClose,
  onChanged,
}: {
  volumeUuid: VolumeUuid;
  volumeName: string;
  onClose: () => void;
  /** Called after a mount or unmount, so the volume list stops showing the old path. */
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [actionError, setActionError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [pathInput, setPathInput] = useState<string>("");
  const [copied, setCopied] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const {
    data: info,
    isPending,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "getVolumeMountInfo", volumeUuid],
    queryFn: () =>
      unwrap<MountInfo>(dispatch("adminQuery", { action: "getVolumeMountInfo", params: { volumeUuid } })),
  });

  const error = actionError ?? errorMessage(queryError, t("vmLoadFailed"));

  /** The path the field submits: what was typed, or the backend's proposal. */
  const proposedPath = pathInput || info?.suggestedPath || "";

  const handleMount = async () => {
    if (!proposedPath) {
      setActionError(t("vmPathRequired"));
      return;
    }
    setActionError(null);
    setResult(null);
    setBusy(true);
    try {
      const data = await adminMutate<{ success?: boolean; junctionPath?: string }>({
        action: "mountVolume",
        params: { volumeUuid, volumeName, junctionPath: proposedPath },
      });
      if (data?.success) {
        setResult(t("vmMounted").replace("{path}", data.junctionPath || proposedPath));
        setPathInput("");
        void refetch();
        onChanged();
      } else setActionError(data?.error || t("vmMountFailed"));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : t("vmMountFailed"));
    } finally {
      setBusy(false);
    }
  };

  const handleUnmount = async () => {
    if (!confirm(t("vmUnmountConfirm").replace("{name}", volumeName))) return;
    setActionError(null);
    setResult(null);
    setBusy(true);
    try {
      const data = await adminMutate<{ success?: boolean; alreadyUnmounted?: boolean; previousPath?: string }>({
        action: "unmountVolume",
        params: { volumeUuid, volumeName, confirm: true },
      });
      if (data?.success) {
        // An already-unmounted volume is reported as such rather than as a successful
        // unmount, because the operator is looking at this panel to find out which it was.
        setResult(
          data.alreadyUnmounted
            ? t("vmAlreadyUnmounted")
            : t("vmUnmounted").replace("{path}", data.previousPath || ""),
        );
        void refetch();
        onChanged();
      } else setActionError(data?.error || t("vmUnmountFailed"));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : t("vmUnmountFailed"));
    } finally {
      setBusy(false);
    }
  };

  const copy = async (label: string, text: string) => {
    setCopied((await copyText(text)) ? label : null);
    setTimeout(() => setCopied(null), 2000);
  };

  const nfsLif = info ? firstUsable(info.nfsLifs) : undefined;

  return (
    <div className="mount-panel">
      <div className="panel-header">
        <h4>
          {t("vmTitle")} — {volumeName}
        </h4>
        <div className="panel-actions">
          <button onClick={() => void refetch()} className="refresh-btn" title={t("refresh")}>
            ↻
          </button>
          <button onClick={onClose} className="btn-secondary">
            {t("close")}
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}
      {result && <div className="success-message">{result}</div>}
      {isPending && <p className="loading">{t("loading")}</p>}

      {info && (
        <>
          <div className="mount-state">
            <span className="mount-label">{t("vmJunctionPath")}</span>
            {info.mounted ? (
              <code className="mount-path">{info.junctionPath}</code>
            ) : (
              <span className="mount-unmounted">{t("vmNotMounted")}</span>
            )}
            <span className="mount-label">SVM</span>
            <code>{info.svm}</code>
          </div>

          {/* An unmounted volume that is also offline cannot be mounted, and saying so
              here saves a round trip through a refusal. The volume list offers the
              bring-online button on the same row. */}
          {!info.mounted && info.state !== "online" && (
            <div className="info-message">{t("vmOfflineFirst").replace("{state}", info.state)}</div>
          )}

          {!info.mounted ? (
            <div className="form-row mount-form">
              <div className="form-group">
                <label>{t("vmMountAt")}</label>
                <input
                  type="text"
                  value={proposedPath}
                  onChange={(e) => setPathInput(e.target.value)}
                  placeholder={info.suggestedPath}
                />
                <small>{t("vmMountAtHint")}</small>
              </div>
              <div className="form-group mount-form-action">
                <button
                  onClick={() => void handleMount()}
                  className="btn-primary"
                  disabled={busy || info.state !== "online"}
                >
                  {t("vmMount")}
                </button>
              </div>
            </div>
          ) : (
            <div className="mount-actions">
              <button onClick={() => void handleUnmount()} className="btn-sm btn-danger" disabled={busy}>
                {t("vmUnmount")}
              </button>
              <small className="rm-hint">{t("vmUnmountHint")}</small>
            </div>
          )}

          {/* ── NFS ─────────────────────────────────────────────────────────── */}
          <div className="mount-protocol">
            <h5>{t("vmNfsTitle")}</h5>
            {info.nfsReady && nfsLif ? (
              <>
                <p className="rm-hint">
                  {t("vmNfsLif")}: <code>{nfsLif.address}</code> ({nfsLif.name})
                </p>
                <div className="vs-code-block">
                  <pre>{nfsCommand(info, nfsLif)}</pre>
                </div>
                <div className="mount-copy-row">
                  <button onClick={() => void copy("nfs", nfsCommand(info, nfsLif))} className="btn-sm">
                    {copied === "nfs" ? t("vmCopied") : t("vmCopy")}
                  </button>
                  <small className="rm-hint">{t("vmClientInVpc")}</small>
                </div>
              </>
            ) : (
              <div className="info-message">
                {/* Three reasons a command cannot be offered, distinguished because the
                    action each calls for is different. */}
                {!info.nfsEnabled
                  ? t("vmNfsDisabled")
                  : !info.mounted
                    ? t("vmNfsNeedsMount")
                    : t("vmNfsNoLif")}
              </div>
            )}
          </div>

          {/* ── SMB ─────────────────────────────────────────────────────────── */}
          <div className="mount-protocol">
            <h5>{t("vmSmbTitle")}</h5>
            {info.smbReady ? (
              <>
                {info.shares.map((share) => (
                  <div key={share.name} className="mount-share">
                    <p className="rm-hint">
                      {share.name} → <code>{share.path}</code>
                      {share.encryption && <span className="badge-lock" title={t("vmSmbEncrypted")}>🔒</span>}
                    </p>
                    <div className="vs-code-block">
                      <pre>{uncPaths(info, share).join("\n")}</pre>
                    </div>
                    <div className="mount-copy-row">
                      <button
                        onClick={() => void copy(share.name, uncPaths(info, share)[0] ?? "")}
                        className="btn-sm"
                      >
                        {copied === share.name ? t("vmCopied") : t("vmCopy")}
                      </button>
                    </div>
                  </div>
                ))}
                <p className="rm-hint">{t("vmSmbHostNote")}</p>
              </>
            ) : (
              <div className="info-message">
                {!info.cifsEnabled ? t("vmSmbDisabled") : !info.mounted ? t("vmNfsNeedsMount") : t("vmSmbNoShare")}
              </div>
            )}
          </div>

          {info.lifError && <div className="error-message">{info.lifError}</div>}
        </>
      )}
    </div>
  );
}
