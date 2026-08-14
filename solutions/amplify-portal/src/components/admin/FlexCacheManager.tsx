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
  /**
   * Which write mode the cache is in, not whether it accepts writes.
   *
   * False is write-around: a write at the cache is forwarded to the origin and
   * acknowledged once the origin has it. True is write-back (ONTAP 9.15.1 and later on
   * both ends): acknowledged at the cache and flushed to the origin asynchronously.
   * NetApp documents both as fully coherent.
   */
  writebackEnabled: boolean;
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
  const [newWriteback, setNewWriteback] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [togglingWriteback, setTogglingWriteback] = useState<string | null>(null);

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
      setError(t("fcacheNameRequired"));
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
          // Only sent when asked for. The handler omits the field entirely otherwise,
          // so a cluster older than 9.15.1 is not handed something it cannot read.
          ...(newWriteback ? { writebackEnabled: true } : {}),
        },
      });
      if (data?.success) {
        setSuccess(t("fcacheCreated"));
        setShowCreate(false);
        setNewName(""); setNewOriginVolume(""); setNewOriginSvm(""); setNewSizeGiB(100); setNewPath("");
        setPrepopulatePaths(""); setNewWriteback(false);
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

  /**
   * Switch an existing cache between write-around and write-back.
   *
   * Disabling flushes whatever is still only at the cache to the origin, and it is the
   * prerequisite for deleting a write-back cache, so it is offered per row rather than
   * only at creation time.
   */
  const handleToggleWriteback = async (cache: FlexCacheVolume) => {
    setError(null);
    setTogglingWriteback(cache.uuid);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "setFlexcacheWriteback",
        params: { uuid: cache.uuid, enabled: !cache.writebackEnabled },
      });
      if (data?.success) {
        setSuccess(cache.writebackEnabled ? t("fcacheWritebackDisabled") : t("fcacheWritebackEnabled"));
        clearSuccess();
        loadCaches();
      } else {
        setError(data?.error || t("rmActionFailed"));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("rmActionFailed"));
    } finally {
      setTogglingWriteback(null);
    }
  };

  const handleDelete = async (cache: FlexCacheVolume) => {
    setError(null); setDeleting(cache.uuid);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "deleteFlexCache",
        params: { uuid: cache.uuid, name: cache.name },
      });
      if (data?.success) {
        setSuccess(t("fcacheDeleted"));
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
        🖥️ {t("fcacheTargetFs")}: default
      </div>

      <div className="lu-toolbar">
        <span className="lu-count">{caches.length} FlexCache volumes</span>
        <button className="rm-btn-primary" onClick={() => setShowCreate(true)} disabled={creating}>
          + FlexCache {t("rmCreate")}
        </button>
      </div>

      {/* Writes come first, because the limits list below reads as "a cache is
          read-only" if the write path is not stated. It is not: a cache accepts writes
          in both modes, and ONTAP keeps the data coherent either way. What the modes
          differ on is where the write is acknowledged. */}
      <details className="vs-guide-section" style={{ marginBottom: "1rem" }}>
        <summary>✍️ {t("fcacheWriteTitle")}</summary>
        <p className="rm-hint">{t("fcacheWriteIntro")}</p>
        <ul className="rm-hint">
          <li>{t("fcacheWriteAround")}</li>
          <li>{t("fcacheWriteBack")}</li>
        </ul>
        <p className="rm-hint">{t("fcacheWriteCoherence")}</p>
        <p className="rm-hint">
          <a
            href="https://docs.netapp.com/us-en/ontap/flexcache-writeback/flexcache-write-back-overview.html"
            target="_blank"
            rel="noopener noreferrer"
          >
            📚 {t("fcacheWriteDocs")}
          </a>
        </p>
      </details>

      {/* Shown whether or not a cache exists. The question "why can I not snapshot
          this volume?" arrives after the cache is created, not before, and the other
          panels now hide cache volumes rather than failing on them -- which is only
          not mysterious if the reason is written down somewhere. */}
      <details className="vs-guide-section" style={{ marginBottom: "1rem" }}>
        <summary>⚠️ {t("fcacheLimitsTitle")}</summary>
        <p className="rm-hint">{t("fcacheLimitsIntro")}</p>
        <ul className="rm-hint">
          <li>{t("fcacheLimitsTiering")}</li>
          <li>{t("fcacheLimitsAtCache")}</li>
          <li>{t("fcacheLimitsSnaplock")}</li>
        </ul>
        <p className="rm-hint">
          <a
            href="https://docs.netapp.com/us-en/ontap/flexcache/supported-unsupported-features-concept.html"
            target="_blank"
            rel="noopener noreferrer"
          >
            📚 {t("fcacheLimitsDocs")}
          </a>
        </p>
      </details>

      {showCreate && (
        <div className="rm-create-form">
          <h4>FlexCache {t("rmCreate")}</h4>
          <p className="rm-hint" style={{ marginBottom: "0.75rem" }}>
            {t("fcacheCreateDesc")}
          </p>
          <div className="rm-form-row">
            <label>{t("fcacheNameLabel")} *</label>
            <input type="text" value={newName} onChange={e => setNewName(e.target.value)}
              placeholder="flexcache_eda_tokyo" disabled={creating} />
          </div>
          <div className="rm-form-row">
            <label>{t("fcacheOriginLabel")} *</label>
            <>
              <input type="text" list="origin-volumes" value={newOriginVolume} onChange={e => setNewOriginVolume(e.target.value)}
                placeholder="vol_production" disabled={creating} />
              <datalist id="origin-volumes">
                {availableVolumes.map(v => <option key={v} value={v} />)}
              </datalist>
            </>
          </div>
          <div className="rm-form-row">
            <label>{t("fcacheOriginSvmLabel")}</label>
            <input type="text" value={newOriginSvm} onChange={e => setNewOriginSvm(e.target.value)}
              placeholder={t("fcacheOriginSvmPlaceholder")} disabled={creating} />
          </div>
          <div className="rm-form-row">
            <label>{t("fcacheSizeLabel")} (GiB)</label>
            <input type="number" min={1} max={100000} value={newSizeGiB}
              onChange={e => setNewSizeGiB(Number(e.target.value))} disabled={creating} />
            <span className="rm-hint" style={{ marginLeft: "0.5rem", fontSize: "0.8rem" }}>
              {t("fcacheSizeHint")}
            </span>
          </div>
          <div className="rm-form-row">
            <label>{t("fcachePathLabel")}</label>
            <input type="text" value={newPath} onChange={e => setNewPath(e.target.value)}
              placeholder={`/${newName || "flexcache_name"}`} disabled={creating} />
          </div>
          <div className="rm-form-row">
            <label>{t("fcachePrepopulateLabel")}</label>
            <input type="text" value={prepopulatePaths} onChange={e => setPrepopulatePaths(e.target.value)}
              placeholder="/data/models/, /cache/datasets/" disabled={creating} />
            <span className="rm-hint" style={{ marginLeft: "0.5rem", fontSize: "0.8rem" }}>
              {t("fcachePrepopulateHint")}
            </span>
          </div>
          <div className="rm-form-row">
            <label htmlFor="fc-writeback">{t("fcacheWritebackLabel")}</label>
            <input
              id="fc-writeback"
              type="checkbox"
              checked={newWriteback}
              onChange={e => setNewWriteback(e.target.checked)}
              disabled={creating}
            />
            <span className="rm-hint" style={{ marginLeft: "0.5rem", fontSize: "0.8rem" }}>
              {t("fcacheWritebackHint")}
            </span>
          </div>
          <div className="rm-form-actions">
            <button
              className="rm-btn-primary"
              onClick={handleCreate}
              disabled={creating}
              aria-label={creating ? (t("fcacheCreating")) : (t("rmCreate"))}
            >
              {creating ? (
                <><span className="spinner" aria-hidden="true"></span> {t("fcacheCreating")}</>
              ) : (
                t("rmCreate")
              )}
            </button>
            <button className="rm-btn-secondary" onClick={() => setShowCreate(false)} disabled={creating}>
              {t("cancel")}
            </button>
          </div>
          {creating && (
            <p className="rm-hint" style={{ marginTop: "0.5rem", color: "var(--color-primary-text)" }}>
              ⏳ {t("fcacheCreatingHint")}
            </p>
          )}
          {!creating && (
            <p className="rm-hint" style={{ marginTop: "0.5rem" }}>
              ⚠️ {t("fcacheAsyncNote")}
            </p>
          )}
        </div>
      )}

      {loading ? (
        <div className="rm-loading">{t("ontapConnecting")}</div>
      ) : caches.length === 0 && !showCreate ? (
        <div className="vs-setup-guide">
          <p className="rm-empty">{t("fcacheNoCaches")}</p>
          <div className="vs-guide-section">
            <h4>💡 {t("fcacheAboutTitle")}</h4>
            <p className="rm-hint">
              {t("fcacheAboutDesc")}
            </p>
            <p className="rm-hint">
              {t("fcacheCreateGuide")}
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
                      <span style={{ background: "var(--color-surface-subtle)", padding: "2px 8px", borderRadius: "4px", fontSize: "0.8rem" }}>
                        📦 {cache.origins[0].volumeName}@{cache.origins[0].svmName}
                      </span>
                    )}
                    <span style={{ color: "var(--color-primary-text)" }}>→</span>
                    <span style={{ background: "var(--color-surface-subtle)", padding: "2px 8px", borderRadius: "4px", fontSize: "0.8rem" }}>
                      ⚡ {cache.name}@{cache.svmName}
                    </span>
                    <span style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
                      {cache.sizeGiB} GiB | {cache.path}
                    </span>
                    {cache.origins.length > 0 && (
                      <span style={{ fontSize: "0.7rem", color: "var(--color-text-secondary)", marginLeft: "0.5rem" }} title="Cache metrics available via ONTAP REST API /storage/flexcache/flexcaches/{uuid}?fields=cache_hit_ratio">
                        📊 {t("fcacheMetricsHint")}
                      </span>
                    )}
                    {cache.globalFileLocking && <span className="lu-badge">🔒 Global Lock</span>}
                    {/* Always shown, in both states: a row with no write badge reads
                        as a cache that does not take writes. */}
                    <span className={`lu-badge ${cache.writebackEnabled ? "active" : ""}`}>
                      ✍️ {cache.writebackEnabled ? t("fcacheModeWriteback") : t("fcacheModeWritearound")}
                    </span>
                  </span>
                </div>
                <div className="lu-group-actions">
                  <span className="lu-badge active">{cache.origins.length} origin(s)</span>
                  <button
                    className="rm-btn-sm"
                    disabled={togglingWriteback === cache.uuid}
                    title={cache.writebackEnabled ? t("fcacheWritebackDisableTitle") : t("fcacheWritebackEnableTitle")}
                    onClick={() => void handleToggleWriteback(cache)}
                  >
                    {togglingWriteback === cache.uuid
                      ? "..."
                      : cache.writebackEnabled
                        ? t("fcacheWritebackDisableAction")
                        : t("fcacheWritebackEnableAction")}
                  </button>
                  <button className="rm-btn-sm" onClick={() => setExpandedUuid(expandedUuid === cache.uuid ? null : cache.uuid)}>
                    {expandedUuid === cache.uuid ? "▼" : "▶"} Origins
                  </button>
                  {confirmDelete === cache.uuid ? (
                    <span style={{ display: "inline-flex", gap: "0.25rem", alignItems: "center" }}>
                      <span style={{ color: "var(--color-error-text)", fontSize: "0.75rem" }}>{t("rmReallyDelete")}</span>
                      <button className="rm-btn-danger-sm" onClick={() => { setConfirmDelete(null); handleDelete(cache); }} disabled={deleting === cache.uuid}>
                        {deleting === cache.uuid ? "..." : t("rmExecute")}
                      </button>
                      <button className="rm-btn-sm" onClick={() => setConfirmDelete(null)}>{t("cancel")}</button>
                    </span>
                  ) : (
                    <button className="rm-btn-danger-sm" onClick={() => setConfirmDelete(cache.uuid)} disabled={deleting === cache.uuid}>
                      {deleting === cache.uuid ? t("rmDeleting") : t("rmDelete")}
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
