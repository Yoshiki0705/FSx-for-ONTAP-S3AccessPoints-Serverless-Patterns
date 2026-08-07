import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage } from "../../lib/portalQuery";
import { adminMutate, adminQuery } from "../../lib/dispatch";

// The client used to be built here with `{ authMode: "userPool" }`. That is already
// the schema's `defaultAuthorizationMode`, so the shared client behaves identically
// and the explicit option was only hiding that it was redundant.

interface FlexCacheOrigin {
  clusterName: string;
  svmName: string;
  volumeName: string;
  state: string;
}

interface FlexCacheVolume {
  name: string;
  uuid: string;
  svmName: string;
  sizeGiB: number;
  path: string;
  origins: FlexCacheOrigin[];
  globalFileLocking: boolean;
}

export function FlexCacheManager() {
  const { t } = useTranslation();
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
  const [success, setSuccess] = useState<string | null>(null);
  const [expandedUuid, setExpandedUuid] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const [newName, setNewName] = useState("");
  const [newOriginVolume, setNewOriginVolume] = useState("");
  const [newOriginSvm, setNewOriginSvm] = useState("");
  const [newSizeGiB, setNewSizeGiB] = useState(100);
  const [newPath, setNewPath] = useState("");
  const [prepopulatePaths, setPrepopulatePaths] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const clearSuccess = () => setTimeout(() => setSuccess(null), 5000);

  const {
    data: caches = [],
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "listFlexCaches"],
    queryFn: async () => {
      const data = await adminQuery<{ caches?: FlexCacheVolume[] }>({ action: "listFlexCaches" });
      // A dispatcher that is not wired yet is an empty list, not a failure.
      if (
        data?.error &&
        !data.error.includes("Unknown action") &&
        !data.error.includes("not configured")
      ) {
        throw new Error(data.error);
      }
      return data?.caches ?? [];
    },
  });

  // Origin candidates only populate the create form, so a failed lookup leaves
  // the field empty rather than blocking the panel.
  const { data: availableVolumes = [] } = useQuery({
    queryKey: ["admin", "flexCacheOriginCandidates"],
    queryFn: async () => {
      const data = await adminQuery<{ volumes?: { name: string }[] }>({ action: "listVolumes" });
      return (data?.volumes ?? []).map((v) => v.name);
    },
  });

  // Mutation handlers report through their own state, so a failed action is
  // never mistaken for a failed load.
  const loadCaches = () => void refetch();
  const error = actionError ?? errorMessage(queryError, "Load failed");

  const handleCreate = async () => {
    if (!newName || !newOriginVolume) {
      setError(t("fcacheNameRequired") || "キャッシュ名とオリジンボリューム名は必須です");
      return;
    }
    setError(null); setCreating(true);
    try {
      const data = await adminMutate<{ success?: boolean; jobId?: string }>({
        action: "createFlexCache",
        params: {
          name: newName,
          originVolume: newOriginVolume,
          originSvm: newOriginSvm || undefined,
          sizeGiB: newSizeGiB,
          path: newPath || `/${newName}`,
          prepopulatePaths: prepopulatePaths ? prepopulatePaths.split(",").map(p => p.trim()).filter(Boolean) : undefined,
        },
      });
      if (data?.success) {
        setSuccess(t("fcacheCreated") || "FlexCache を作成しました（バックグラウンドで構築中）");
        setShowCreate(false);
        setNewName(""); setNewOriginVolume(""); setNewOriginSvm(""); setNewSizeGiB(100); setNewPath("");
        setPrepopulatePaths("");
        clearSuccess();
        // Progressive refresh: ONTAP FlexCache creation is async (30-120s typically)
        setTimeout(() => loadCaches(), 10000);
        setTimeout(() => loadCaches(), 30000);
        setTimeout(() => loadCaches(), 60000);
      } else {
        setError(data?.error || t("fcacheCreateFailed"));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("fcacheCreateFailed"));
    } finally { setCreating(false); }
  };

  const handleDelete = async (cache: FlexCacheVolume) => {
    setError(null); setDeleting(cache.uuid);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "deleteFlexCache",
        params: { uuid: cache.uuid, name: cache.name },
      });
      if (data?.success) {
        setSuccess(t("fcacheDeleted") || `FlexCache "${cache.name}" を削除しました`);
        clearSuccess(); loadCaches();
      } else {
        setError(data?.error || t("fcacheDeleteFailed"));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("fcacheDeleteFailed"));
    } finally { setDeleting(null); }
  };

  return (
    <div className="flexcache-manager">
      {error && <div className="rm-error">⚠️ {error}</div>}
      {success && <div className="rm-success">✅ {success}</div>}

      {/* Multi-FS indicator */}
      <div className="rm-hint" style={{ marginBottom: "0.5rem", fontSize: "0.75rem", opacity: 0.7 }}>
        {/*
          Reads "default" because that is the file system the backend targets. This
          was `(window as any).__PORTAL_CONFIG?.ontapMgmtIp || "default"`, but nothing
          in the repository ever assigns `window.__PORTAL_CONFIG` — not index.html, not
          a Vite `define`, not the backend — so the lookup was always undefined and the
          fallback always won. Rendering the same string directly keeps the output
          identical without an `any` cast over a global that does not exist.

          It is deliberately not wired up: the management IP lives in portal-config.ts,
          which is gitignored precisely because it holds internal addresses. Publishing
          one to the browser bundle would leak it to every signed-in user.
        */}
        🖥️ {t("fcacheTargetFs") || "接続先"}: default
      </div>

      <div className="lu-toolbar">
        <span className="lu-count">{caches.length} FlexCache volumes</span>
        <button className="rm-btn-primary" onClick={() => setShowCreate(true)} disabled={creating}>
          + FlexCache {t("rmCreate") || "作成"}
        </button>
      </div>

      {showCreate && (
        <div className="rm-create-form">
          <h4>FlexCache {t("rmCreate") || "作成"}</h4>
          <p className="rm-hint" style={{ marginBottom: "0.75rem" }}>
            {t("fcacheCreateDesc") || "オリジンボリュームの読み取りデータをローカルにキャッシュするボリュームを作成します。推奨サイズはオリジンの 10%〜20% です。"}
          </p>
          <div className="rm-form-row">
            <label>{t("fcacheNameLabel") || "キャッシュ名"} *</label>
            <input type="text" value={newName} onChange={e => setNewName(e.target.value)}
              placeholder="flexcache_eda_tokyo" disabled={creating} />
          </div>
          <div className="rm-form-row">
            <label>{t("fcacheOriginLabel") || "オリジンボリューム名"} *</label>
            <>
              <input type="text" list="origin-volumes" value={newOriginVolume} onChange={e => setNewOriginVolume(e.target.value)}
                placeholder="vol_production" disabled={creating} />
              <datalist id="origin-volumes">
                {availableVolumes.map(v => <option key={v} value={v} />)}
              </datalist>
            </>
          </div>
          <div className="rm-form-row">
            <label>{t("fcacheOriginSvmLabel") || "オリジン SVM（同一 SVM なら空欄可）"}</label>
            <input type="text" value={newOriginSvm} onChange={e => setNewOriginSvm(e.target.value)}
              placeholder={t("fcacheOriginSvmPlaceholder") || "同一 SVM の場合は空欄"} disabled={creating} />
          </div>
          <div className="rm-form-row">
            <label>{t("fcacheSizeLabel") || "サイズ"} (GiB)</label>
            <input type="number" min={1} max={100000} value={newSizeGiB}
              onChange={e => setNewSizeGiB(Number(e.target.value))} disabled={creating} />
            <span className="rm-hint" style={{ marginLeft: "0.5rem", fontSize: "0.8rem" }}>
              {t("fcacheSizeHint") || "推奨: オリジンの 10%。最小 1 GiB"}
            </span>
          </div>
          <div className="rm-form-row">
            <label>{t("fcachePathLabel") || "ジャンクションパス"}</label>
            <input type="text" value={newPath} onChange={e => setNewPath(e.target.value)}
              placeholder={`/${newName || "flexcache_name"}`} disabled={creating} />
          </div>
          <div className="rm-form-row">
            <label>{t("fcachePrepopulateLabel") || "プリポピュレートパス"}</label>
            <input type="text" value={prepopulatePaths} onChange={e => setPrepopulatePaths(e.target.value)}
              placeholder="/data/models/, /cache/datasets/" disabled={creating} />
            <span className="rm-hint" style={{ marginLeft: "0.5rem", fontSize: "0.8rem" }}>
              {t("fcachePrepopulateHint") || "カンマ区切りで事前読み込みするパスを指定（オプション）"}
            </span>
          </div>
          <div className="rm-form-actions">
            <button
              className="rm-btn-primary"
              onClick={handleCreate}
              disabled={creating}
              aria-label={creating ? (t("fcacheCreating") || "作成中") : (t("rmCreate") || "作成")}
            >
              {creating ? (
                <><span className="spinner" aria-hidden="true"></span> {t("fcacheCreating") || "作成中..."}</>
              ) : (
                t("rmCreate") || "作成"
              )}
            </button>
            <button className="rm-btn-secondary" onClick={() => setShowCreate(false)} disabled={creating}>
              {t("cancel") || "キャンセル"}
            </button>
          </div>
          {creating && (
            <p className="rm-hint" style={{ marginTop: "0.5rem", color: "var(--accent-color, #0066cc)" }}>
              ⏳ {t("fcacheCreatingHint") || "ONTAP に FlexCache 作成を要求しています...（数十秒〜数分かかります）"}
            </p>
          )}
          {!creating && (
            <p className="rm-hint" style={{ marginTop: "0.5rem" }}>
              ⚠️ {t("fcacheAsyncNote") || "FlexCache 作成はバックグラウンドで実行されます（数十秒〜数分）。作成後、一覧に表示されるまで少し時間がかかることがあります。"}
            </p>
          )}
        </div>
      )}

      {loading ? (
        <div className="rm-loading">{t("ontapConnecting") || "接続中..."}</div>
      ) : caches.length === 0 && !showCreate ? (
        <div className="vs-setup-guide">
          <p className="rm-empty">{t("fcacheNoCaches") || "FlexCache ボリュームがありません"}</p>
          <div className="vs-guide-section">
            <h4>💡 {t("fcacheAboutTitle") || "FlexCache とは"}</h4>
            <p className="rm-hint">
              {t("fcacheAboutDesc") || "FlexCache はリモートボリュームのデータをローカルにキャッシュする読み取り高速化機能です。複数サイトからのアクセスが多いワークロード（EDA/CAD、ビルドパイプライン、AI 推論データ等）で、ネットワーク越しのレイテンシを削減します。"}
            </p>
            <p className="rm-hint">
              {t("fcacheCreateGuide") || "上の「+ FlexCache 作成」ボタンからオリジンボリュームを指定して作成できます。"}
            </p>
            <p className="rm-hint">
              <a href="https://docs.netapp.com/us-en/ontap/flexcache/index.html" target="_blank" rel="noopener noreferrer">
                📚 FlexCache (NetApp Docs)
              </a>
              {" | "}
              <a href="https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-volumes.html" target="_blank" rel="noopener noreferrer">
                📖 FSx for ONTAP (AWS Docs)
              </a>
            </p>
          </div>
        </div>
      ) : (
        <div className="lu-groups-list">
          {caches.map(cache => (
            <div key={cache.uuid} className="lu-group-card">
              <div className="lu-group-header">
                <div className="lu-group-info">
                  <span className="lu-group-name">⚡ {cache.name}</span>
                  <span className="lu-group-desc" style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                    {cache.origins.length > 0 && (
                      <span style={{ background: "var(--surface-color, #f0f4f8)", padding: "2px 8px", borderRadius: "4px", fontSize: "0.8rem" }}>
                        📦 {cache.origins[0].volumeName}@{cache.origins[0].svmName}
                      </span>
                    )}
                    <span style={{ color: "var(--accent-color, #0066cc)" }}>→</span>
                    <span style={{ background: "var(--surface-color, #f0f4f8)", padding: "2px 8px", borderRadius: "4px", fontSize: "0.8rem" }}>
                      ⚡ {cache.name}@{cache.svmName}
                    </span>
                    <span style={{ fontSize: "0.75rem", color: "#666" }}>
                      {cache.sizeGiB} GiB | {cache.path}
                    </span>
                    {cache.origins.length > 0 && (
                      <span style={{ fontSize: "0.7rem", color: "#718096", marginLeft: "0.5rem" }} title="Cache metrics available via ONTAP REST API /storage/flexcache/flexcaches/{uuid}?fields=cache_hit_ratio">
                        📊 {t("fcacheMetricsHint")}
                      </span>
                    )}
                    {cache.globalFileLocking && <span className="lu-badge">🔒 Global Lock</span>}
                  </span>
                </div>
                <div className="lu-group-actions">
                  <span className="lu-badge active">{cache.origins.length} origin(s)</span>
                  <button className="rm-btn-sm" onClick={() => setExpandedUuid(expandedUuid === cache.uuid ? null : cache.uuid)}>
                    {expandedUuid === cache.uuid ? "▼" : "▶"} Origins
                  </button>
                  {confirmDelete === cache.uuid ? (
                    <span style={{ display: "inline-flex", gap: "0.25rem", alignItems: "center" }}>
                      <span style={{ color: "#e53e3e", fontSize: "0.75rem" }}>{t("rmReallyDelete")}</span>
                      <button className="rm-btn-danger-sm" onClick={() => { setConfirmDelete(null); handleDelete(cache); }} disabled={deleting === cache.uuid}>
                        {deleting === cache.uuid ? "..." : t("rmExecute")}
                      </button>
                      <button className="rm-btn-sm" onClick={() => setConfirmDelete(null)}>{t("cancel")}</button>
                    </span>
                  ) : (
                    <button className="rm-btn-danger-sm" onClick={() => setConfirmDelete(cache.uuid)} disabled={deleting === cache.uuid}>
                      {deleting === cache.uuid ? "削除中..." : (t("rmDelete") || "削除")}
                    </button>
                  )}
                </div>
              </div>
              {expandedUuid === cache.uuid && (
                <div className="lu-members-panel">
                  {cache.origins.length === 0 ? (
                    <p className="rm-empty-sm">{t("fcNoOrigins")}</p>
                  ) : (
                    <table className="rm-table" style={{ fontSize: "0.85rem" }}>
                      <thead><tr><th>{t("fcOriginCluster")}</th><th>{t("fcOriginSvm")}</th><th>{t("fcOriginVolume")}</th><th>State</th></tr></thead>
                      <tbody>
                        {cache.origins.map((origin, i) => (
                          <tr key={i}>
                            <td>{origin.clusterName || "—"}</td>
                            <td>{origin.svmName}</td>
                            <td className="lu-username">{origin.volumeName}</td>
                            <td><span className={`lu-badge ${origin.state === "online" ? "active" : ""}`}>{origin.state}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
