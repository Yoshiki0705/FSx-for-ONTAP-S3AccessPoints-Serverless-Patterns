import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";

const client = generateClient<Schema>({ authMode: "userPool" });

function parseResponse<T>(response: { data?: string | null }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === "string" ? JSON.parse(response.data) : response.data;
  } catch { return null; }
}

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
  const [caches, setCaches] = useState<FlexCacheVolume[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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
  const [availableVolumes, setAvailableVolumes] = useState<string[]>([]);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const clearSuccess = () => setTimeout(() => setSuccess(null), 5000);

  const loadCaches = async () => {
    setLoading(true); setError(null);
    try {
      const resp = await (client.queries as any).adminQuery({
        action: "listFlexCaches", params: JSON.stringify({}),
      });
      const data = parseResponse<{ caches?: FlexCacheVolume[]; error?: string }>(resp);
      if (data?.error && !data.error.includes("Unknown action") && !data.error.includes("not configured")) {
        setError(data.error);
      } else {
        setCaches(data?.caches || []);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    } finally { setLoading(false); }
  };

  useEffect(() => {
    loadCaches();
    // Fetch available volumes for origin selection
    (client.queries as any).adminQuery({ action: "listVolumes", params: JSON.stringify({}) })
      .then((resp: any) => {
        const data = parseResponse<{ volumes?: { name: string }[] }>(resp);
        if (data?.volumes) setAvailableVolumes(data.volumes.map(v => v.name));
      }).catch(() => {});
  }, []);

  const handleCreate = async () => {
    if (!newName || !newOriginVolume) {
      setError(t("fcacheNameRequired") || "キャッシュ名とオリジンボリューム名は必須です");
      return;
    }
    setError(null); setCreating(true);
    try {
      const resp = await (client.mutations as any).adminMutation({
        action: "createFlexCache",
        params: JSON.stringify({
          name: newName,
          originVolume: newOriginVolume,
          originSvm: newOriginSvm || undefined,
          sizeGiB: newSizeGiB,
          path: newPath || `/${newName}`,
          prepopulatePaths: prepopulatePaths ? prepopulatePaths.split(",").map(p => p.trim()).filter(Boolean) : undefined,
        }),
      });
      const data = parseResponse<{ success?: boolean; error?: string; jobId?: string }>(resp);
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
        setError(data?.error || t("fcacheCreateFailed") || "作成に失敗しました");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "作成に失敗しました");
    } finally { setCreating(false); }
  };

  const handleDelete = async (cache: FlexCacheVolume) => {
    setError(null); setDeleting(cache.uuid);
    try {
      const resp = await (client.mutations as any).adminMutation({
        action: "deleteFlexCache",
        params: JSON.stringify({ uuid: cache.uuid, name: cache.name }),
      });
      const data = parseResponse<{ success?: boolean; error?: string }>(resp);
      if (data?.success) {
        setSuccess(t("fcacheDeleted") || `FlexCache "${cache.name}" を削除しました`);
        clearSuccess(); loadCaches();
      } else {
        setError(data?.error || t("fcacheDeleteFailed") || "削除に失敗しました");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "削除に失敗しました");
    } finally { setDeleting(null); }
  };

  return (
    <div className="flexcache-manager">
      {error && <div className="rm-error">⚠️ {error}</div>}
      {success && <div className="rm-success">✅ {success}</div>}

      {/* Multi-FS indicator */}
      <div className="rm-hint" style={{ marginBottom: "0.5rem", fontSize: "0.75rem", opacity: 0.7 }}>
        🖥️ {t("fcacheTargetFs") || "接続先"}: {(window as any).__PORTAL_CONFIG?.ontapMgmtIp || "default"}
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
                        📊 メトリクス: ONTAP System Manager で確認可
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
