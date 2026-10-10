import { useState } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "../i18n";
import type { TranslationKeys } from "../i18n/locales/ja";
import { errorMessage } from "../lib/portalQuery";
import { recoveryPointsQuery, restoreMutate } from "../lib/dispatch";
import { useStorageAdmin } from "../hooks/useStorageAdmin";
import { restoreAllowedSvmIds } from "../lib/portalOutputs";
import { RestoreConfirmDialog, type RestoreFormValues } from "./RestoreConfirmDialog";

/**
 * One AWS Backup recovery point, as the handler returns it.
 *
 * These are AWS Backup objects, not ONTAP snapshots. The panel labels them as
 * such so the two are not confused — the storage location and the management
 * boundary differ (see docs/data-protection-recovery-design.md).
 */
interface RecoveryPoint {
  recoveryPointArn: string;
  resourceArn: string;
  resourceType: string;
  creationDate: string;
  status: string;
  statusMessage: string;
  backupVaultName: string;
  /** The vault's ARN; carries the owner's account ID and the Region. */
  backupVaultArn?: string;
  /** The account that owns the vault. Another account's ID for a shared vault. */
  ownerAccountId?: string;
  /** The Region the vault is in. Absent from a handler that predates #461. */
  region?: string;
  /** Passed through from the row, because a shared vault is not in this account's own vault list. */
  vaultType?: string;
  isEncrypted: boolean;
  encryptionKeyArn: string;
  backupSizeInBytes: number;
}

interface BackupVault {
  backupVaultName: string;
  backupVaultArn: string;
  ownerAccountId: string;
  /** True for a vault this account owns; such a row is not offered as a shared vault. */
  ownedByThisAccount: boolean;
  region: string;
  vaultType: string;
  vaultState: string;
  encryptionKeyType: string;
  locked: boolean;
  numberOfRecoveryPoints: number;
}

/**
 * What the handler answers on every path: the payload, plus an in-band error and a
 * code. The panel branches on `errorCode`; it never reads the message to work out
 * what went wrong.
 */
interface HandlerStatus {
  error?: string | null;
  errorCode?: string | null;
}

interface RecoveryPointsResponse extends HandlerStatus {
  recoveryPoints?: RecoveryPoint[];
}

interface VaultsResponse extends HandlerStatus {
  backupVaults?: BackupVault[];
  /** The Region the list is for. */
  region?: string;
  /**
   * The Region the portal's function runs in: the only one a restore can be started in.
   * The handler puts this and `regions` on failures too, but a rejected request carries
   * no body at all, so the panel also keeps the first answer it received.
   */
  homeRegion?: string;
  /** The Regions the selector offers: home first, then the configured ones. */
  regions?: string[];
}

/** The Region context the panel keeps once it has learned it. */
interface RegionContext {
  homeRegion: string;
  regions: string[];
}

const UNKNOWN_REGION_CONTEXT: RegionContext = { homeRegion: "", regions: [] };

/**
 * Which vault the table shows.
 *
 * `default` is the configured vault set of this account's home Region (the #459
 * view). `local` and `shared` name one vault; a shared vault is identified by its
 * owner account as well, because a name is unique only per (account, Region).
 */
type VaultSelection =
  | { kind: "default" }
  | { kind: "local"; name: string }
  | { kind: "shared"; accountId: string; name: string };

const DEFAULT_SELECTION: VaultSelection = { kind: "default" };

/** The value of a vault `<option>`. Vault names cannot contain `:`. */
function selectionValue(selection: VaultSelection): string {
  if (selection.kind === "local") return `local:${selection.name}`;
  if (selection.kind === "shared") return `shared:${selection.accountId}:${selection.name}`;
  return "default";
}

function parseSelection(value: string): VaultSelection {
  const [kind, first, ...rest] = value.split(":");
  if (kind === "local" && first) return { kind: "local", name: [first, ...rest].join(":") };
  if (kind === "shared" && first && rest.length > 0) return { kind: "shared", accountId: first, name: rest.join(":") };
  return DEFAULT_SELECTION;
}

const LOGICALLY_AIR_GAPPED = "LOGICALLY_AIR_GAPPED_BACKUP_VAULT";

/**
 * Where the monitoring this panel does not do is described. Job failures,
 * "Completed with issues" and AWS RAM share revocation are detected by the
 * Observability integrations; the portal only points there. Pages, not heading
 * fragments: the relevant text is in quoted notes, and a fragment that stops
 * matching sends the reader to the top of the page without saying so.
 */
const OBSERVABILITY_DOCS = {
  ja: "https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/ja/cyber-resilience-capability-map.md",
  en: "https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations/blob/main/docs/en/cyber-resilience-capability-map.md",
} as const;

const SMALL_TEXT_STYLE = { fontSize: "0.8rem", color: "var(--color-text-secondary)" } as const;

/** A recovery point must be in one of these states to be restorable. */
const RESTORABLE_STATUSES = new Set(["AVAILABLE", "COMPLETED"]);

/**
 * Capacity-pool tiering policies offered in the restore form.
 *
 * The default (first entry) matches the ONTAP restore default. These are the FSx
 * for ONTAP tiering policy names; the handler passes the chosen value through to the
 * restore Metadata unchanged.
 */
const TIERING_POLICIES = ["SNAPSHOT_ONLY", "AUTO", "ALL", "NONE"];

/**
 * The label and severity for a recovery-point Status.
 *
 * The enum is COMPLETED | PARTIAL | DELETING | EXPIRED | AVAILABLE | STOPPED |
 * CREATING. An unmapped value is shown verbatim rather than hidden, so a status
 * added to the enum later is never silently dropped. "Completed with issues" is a
 * copy-/backup-job state, not a recovery-point Status, so nothing keys on it here;
 * the raw Status and StatusMessage are surfaced as-is.
 */
const STATUS_LABELS: Record<string, { key: TranslationKeys; severity: "online" | "warning" | "offline" }> = {
  AVAILABLE: { key: "rpStatusAvailable", severity: "online" },
  COMPLETED: { key: "rpStatusAvailable", severity: "online" },
  CREATING: { key: "rpStatusCreating", severity: "warning" },
  PARTIAL: { key: "rpStatusPartial", severity: "warning" },
  STOPPED: { key: "rpStatusStopped", severity: "warning" },
  EXPIRED: { key: "rpStatusExpired", severity: "warning" },
  DELETING: { key: "rpStatusDeleting", severity: "warning" },
};

function formatSize(bytes: number): string {
  if (!bytes) return "—";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

/**
 * Recovery points — list of AWS Backup recovery points (#459), restorable into a new
 * volume (#460), across Regions and shared vaults (#461).
 *
 * Deliberately distinct from the "ONTAP Snapshots" panel: a cloud header, an
 * explicit sub-line stating these are AWS Backup points, and a vault-type chip for
 * logically air-gapped vaults. One table serves every scope: this account's
 * configured vaults, one named vault in a selectable Region, or a vault another
 * account shared through AWS RAM. No malware-scan column: FSx for ONTAP is out of
 * scope for Malware Protection for AWS Backup, so a same-named column would mislead.
 *
 * Restores are started in the portal's own Region only, so a row from another Region
 * is listed but its restore button is disabled. Job failures, "Completed with
 * issues" and share revocation are not monitored here; the panel links to the
 * Observability integrations that do.
 */
export function RecoveryPoints() {
  const { t, locale } = useTranslation();
  const isStorageAdmin = useStorageAdmin();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  /** The Region being read; "" is the portal's own. */
  const [region, setRegion] = useState("");
  const [selection, setSelection] = useState<VaultSelection>(DEFAULT_SELECTION);
  /**
   * The home Region and the selectable Regions, kept from the first answer that carried
   * them. They are configuration, not per-Region data, so a later failed or rejected
   * vault-list request (an opt-in Region that is not enabled, throttling, a network
   * error) must not clear them: the selector is built from them, and so is the way back.
   */
  const [regionContext, setRegionContext] = useState<RegionContext>(UNKNOWN_REGION_CONTEXT);
  /** Set when the selected shared vault disappears from the shared list. */
  const [sharedVaultGone, setSharedVaultGone] = useState(false);
  /** The recovery point whose restore dialog is open; null when none. */
  const [pendingRestore, setPendingRestore] = useState<RecoveryPoint | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [restoreResult, setRestoreResult] = useState<string | null>(null);

  const runRestore = async (point: RecoveryPoint, values: RestoreFormValues) => {
    setRestoreError(null);
    setRestoreResult(null);
    try {
      const data = await restoreMutate<{ restoreJobId?: string }>({
        action: "startRestore",
        params: {
          recoveryPointArn: point.recoveryPointArn,
          name: values.name,
          storageVirtualMachineId: values.storageVirtualMachineId,
          junctionPath: values.junctionPath,
          sizeInMegabytes: values.sizeInMegabytes,
          storageEfficiencyEnabled: values.storageEfficiencyEnabled,
          tieringPolicy: values.tieringPolicy,
          acknowledgeIrreversible: true,
        },
      });
      if (data?.error) {
        setRestoreError(data.error);
      } else if (data?.restoreJobId) {
        setRestoreResult(t("rpRestoreStarted").split("{jobId}").join(data.restoreJobId));
      } else {
        setRestoreError(t("rpRestoreError"));
      }
    } catch (err) {
      setRestoreError(err instanceof Error ? err.message : t("rpRestoreError"));
    }
  };

  // The vault lists. They are keyed by Region, and the previous Region's answer is
  // kept while the next one loads, so the Region selector (which is built from this
  // answer) stays on screen instead of vanishing mid-click.
  const vaultsQuery = useQuery({
    queryKey: ["recoveryPoints", "listBackupVaults", region],
    queryFn: () =>
      recoveryPointsQuery<VaultsResponse>({
        action: "listBackupVaults",
        params: { backupVaultRegion: region || undefined },
      }),
    placeholderData: keepPreviousData,
  });

  const sharedQuery = useQuery({
    queryKey: ["recoveryPoints", "listSharedBackupVaults", region],
    queryFn: () =>
      recoveryPointsQuery<VaultsResponse>({
        action: "listSharedBackupVaults",
        params: { backupVaultRegion: region || undefined },
      }),
  });

  const answeredHomeRegion = vaultsQuery.data?.homeRegion ?? "";
  const answeredRegions = vaultsQuery.data?.regions ?? [];
  // Adjusted while rendering, like the selection below: the condition is false on the
  // pass that follows, so it cannot loop.
  if (regionContext.homeRegion === "" && answeredHomeRegion !== "" && answeredRegions.length > 0) {
    setRegionContext({ homeRegion: answeredHomeRegion, regions: answeredRegions });
  }
  const homeRegion = regionContext.homeRegion || answeredHomeRegion;
  const regions = regionContext.regions.length > 0 ? regionContext.regions : answeredRegions;
  const isHomeRegion = region === "" || region === homeRegion;
  // Outside the home Region there is no configured default: a vault name is unique
  // per Region, so the handler needs one named. Until one is chosen the table asks.
  const needsVaultChoice = !isHomeRegion && selection.kind === "default";

  const vaults = vaultsQuery.isPlaceholderData ? [] : (vaultsQuery.data?.backupVaults ?? []);
  // Not while the previous Region's answer is standing in: its error is not this Region's.
  const vaultsLoadError = vaultsQuery.isPlaceholderData
    ? null
    : (errorMessage(vaultsQuery.error, "") ?? vaultsQuery.data?.error ?? null);
  const sharedListOk = sharedQuery.isSuccess && !sharedQuery.data?.error;
  // Rows this account owns are not "shared with" it, whichever list ByShared returned.
  const sharedVaults = sharedListOk ? (sharedQuery.data?.backupVaults ?? []).filter((v) => !v.ownedByThisAccount) : [];
  const sharedLoadError = errorMessage(sharedQuery.error, "") ?? sharedQuery.data?.error ?? null;
  const vaultByName = new Map(vaults.map((v) => [v.backupVaultName, v]));

  const selectedName = selection.kind === "default" ? "" : selection.name;
  const selectedAccountId = selection.kind === "shared" ? selection.accountId : "";

  const pointsQuery = useQuery({
    queryKey: ["recoveryPoints", "listRecoveryPoints", region, selectedAccountId, selectedName],
    queryFn: async (): Promise<RecoveryPointsResponse | null> => {
      if (needsVaultChoice) return { recoveryPoints: [] };
      const data = await recoveryPointsQuery<RecoveryPointsResponse>({
        action: "listRecoveryPoints",
        params: {
          maxResults: 100,
          backupVaultRegion: region || undefined,
          backupVaultName: selectedName || undefined,
          backupVaultAccountId: selectedAccountId || undefined,
        },
      });
      // The handler can learn that a share is gone before the shared list is fetched
      // again. Ask for that list now, so the revoked vault does not stay in the
      // selector until the next refresh. Here, after the response, not during render.
      if (data?.errorCode === "VaultNotShared") {
        void queryClient.invalidateQueries({ queryKey: ["recoveryPoints", "listSharedBackupVaults", region] });
      }
      return data;
    },
  });

  // A shared vault the user picked can leave the shared list: the owner revoked the
  // AWS RAM share, or it was never accepted. Two signals say so — the list no longer
  // has it, or the handler answers VaultNotShared — and both return the panel to its
  // default view with a notice rather than leaving it on a vault that no longer exists.
  const selectedShared = selection.kind === "shared" ? selection : null;
  const stillShared =
    selectedShared === null ||
    sharedVaults.some(
      (v) => v.backupVaultName === selectedShared.name && v.ownerAccountId === selectedShared.accountId,
    );
  const reportedNotShared = pointsQuery.data?.errorCode === "VaultNotShared";
  // Adjusted while rendering rather than in an effect: React re-renders at once with
  // the new state, and the condition is false on that pass (nothing shared is selected
  // any more), so it cannot loop.
  if (selectedShared !== null && ((sharedListOk && !stillShared) || reportedNotShared)) {
    setSelection(DEFAULT_SELECTION);
    setSharedVaultGone(true);
  }

  const points = pointsQuery.data?.recoveryPoints ?? [];
  const loadError = errorMessage(pointsQuery.error, "") ?? pointsQuery.data?.error ?? null;
  const accessDenied = pointsQuery.data?.errorCode === "AccessDeniedException";

  const visiblePoints = statusFilter ? points.filter((p) => p.status === statusFilter) : points;
  const statuses = Array.from(new Set(points.map((p) => p.status))).filter(Boolean).sort();

  const changeRegion = (next: string) => {
    setRegion(next === homeRegion ? "" : next);
    setSelection(DEFAULT_SELECTION);
    setSharedVaultGone(false);
    setStatusFilter("");
  };

  const changeSelection = (value: string) => {
    setSelection(parseSelection(value));
    setSharedVaultGone(false);
    setStatusFilter("");
  };

  const refresh = () => {
    void pointsQuery.refetch();
    void vaultsQuery.refetch();
    void sharedQuery.refetch();
  };

  const formatDate = (iso: string) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  const statusCell = (point: RecoveryPoint) => {
    const mapped = STATUS_LABELS[point.status];
    const label = mapped ? t(mapped.key) : point.status || "—";
    const severity = mapped ? mapped.severity : "offline";
    return (
      <>
        <span className={`state-badge state-${severity}`}>{label}</span>
        {point.statusMessage && <div style={SMALL_TEXT_STYLE}>{point.statusMessage}</div>}
      </>
    );
  };

  const vaultSelectValue = needsVaultChoice ? "" : selectionValue(selection);
  const observabilityHref = locale === "ja" ? OBSERVABILITY_DOCS.ja : OBSERVABILITY_DOCS.en;

  return (
    <div className="protection-section">
      <div className="protection-header">
        <h2>☁️ {t("rpTitle")}</h2>
        <button onClick={refresh} className="refresh-btn" aria-label={t("refresh")}>
          ↻
        </button>
      </div>
      <p className="status-subtitle" style={{ display: "block", marginBottom: "1rem" }}>
        {t("rpSubtitle")}
      </p>

      {/* The selectors sit outside the loading state: replacing the panel with a
          spinner while a selection loads would remove the control being used. */}
      {regions.length > 1 && (
        <div className="form-group" style={{ maxWidth: "20rem", marginBottom: "1rem" }}>
          <label htmlFor="rp-region">{t("rpRegionLabel")}</label>
          <select id="rp-region" value={region || homeRegion} onChange={(e) => changeRegion(e.target.value)}>
            {regions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="form-group" style={{ maxWidth: "28rem", marginBottom: "1rem" }}>
        <label htmlFor="rp-vault-scope">{t("rpScopeLabel")}</label>
        <select id="rp-vault-scope" value={vaultSelectValue} onChange={(e) => changeSelection(e.target.value)}>
          {isHomeRegion ? (
            <option value="default">{t("rpScopeDefault")}</option>
          ) : (
            <option value="">—</option>
          )}
          {vaults.length > 0 && (
            <optgroup label={t("rpScopeLocalGroup")}>
              {vaults.map((v) => (
                <option key={v.backupVaultArn || v.backupVaultName} value={selectionValue({ kind: "local", name: v.backupVaultName })}>
                  {v.backupVaultName}
                </option>
              ))}
            </optgroup>
          )}
          {sharedVaults.length > 0 && (
            <optgroup label={t("rpScopeSharedGroup")}>
              {sharedVaults.map((v) => (
                <option
                  key={v.backupVaultArn || `${v.ownerAccountId}/${v.backupVaultName}`}
                  value={selectionValue({ kind: "shared", accountId: v.ownerAccountId, name: v.backupVaultName })}
                >
                  {v.ownerAccountId} / {v.backupVaultName}
                </option>
              ))}
            </optgroup>
          )}
        </select>
      </div>
      {sharedListOk && sharedVaults.length === 0 && (
        <p className="status-subtitle" style={{ display: "block", marginBottom: "1rem" }}>
          {t("rpNoSharedVaults")}
        </p>
      )}
      {sharedLoadError && (
        <div className="error-message">
          {t("rpSharedLoadError")}: {sharedLoadError}
        </div>
      )}
      {vaultsLoadError && (
        <div className="error-message">
          {t("rpVaultsLoadError")}: {vaultsLoadError}
        </div>
      )}
      {sharedVaultGone && <div className="info-message">{t("rpSharedVaultGone")}</div>}
      {selectedShared !== null && isStorageAdmin === true && (
        <p className="status-subtitle" style={{ display: "block", marginBottom: "1rem" }}>
          {t("rpSharedRestoreNote")}
        </p>
      )}

      {loadError && (
        <div className="error-message">
          {t("rpLoadError")}: {loadError}
        </div>
      )}
      {accessDenied && (
        // Share revocation and an unaccepted share can only explain a refusal on a shared
        // vault; for a vault of this account only the IAM ARN scope is in play.
        <div className="error-message">{t(selectedShared !== null ? "rpAccessDeniedHint" : "rpAccessDeniedHintOwn")}</div>
      )}
      {restoreError && <div className="error-message">{t("rpRestoreError")}: {restoreError}</div>}
      {restoreResult && <div className="success-message">{restoreResult}</div>}

      {pendingRestore && (
        <RestoreConfirmDialog
          recoveryPointArn={pendingRestore.recoveryPointArn}
          allowedSvmIds={restoreAllowedSvmIds}
          tieringPolicies={TIERING_POLICIES}
          onCancel={() => setPendingRestore(null)}
          onConfirm={(values) => {
            const point = pendingRestore;
            setPendingRestore(null);
            void runRestore(point, values);
          }}
        />
      )}

      {statuses.length > 0 && (
        <div className="form-group" style={{ maxWidth: "20rem", marginBottom: "1rem" }}>
          <label>{t("rpColStatus")}</label>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">—</option>
            {statuses.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s] ? t(STATUS_LABELS[s].key) : s}
              </option>
            ))}
          </select>
        </div>
      )}

      {pointsQuery.isPending ? (
        <p className="loading">{t("loading")}</p>
      ) : visiblePoints.length > 0 ? (
        <table className="admin-table">
          <thead>
            <tr>
              <th>{t("rpColCreated")}</th>
              <th>{t("rpColStatus")}</th>
              <th>{t("rpColResourceType")}</th>
              <th>{t("rpColSize")}</th>
              <th>{t("rpColVault")}</th>
              <th>{t("rpColEncryption")}</th>
              {isStorageAdmin === true && <th>{t("rpColActions")}</th>}
            </tr>
          </thead>
          <tbody>
            {visiblePoints.map((point) => {
              const vault = vaultByName.get(point.backupVaultName);
              // The row's own type first: a shared vault is not in this account's list.
              const airGapped = (point.vaultType || vault?.vaultType) === LOGICALLY_AIR_GAPPED;
              // Fails closed: a restore is started in the portal's own Region, so a row that
              // names a Region is restorable only when that Region is known to be the same.
              const inOtherRegion = Boolean(point.region) && point.region !== homeRegion;
              return (
                <tr key={point.recoveryPointArn}>
                  <td>{formatDate(point.creationDate)}</td>
                  <td>{statusCell(point)}</td>
                  <td>{point.resourceType || "—"}</td>
                  <td>{formatSize(point.backupSizeInBytes)}</td>
                  <td>
                    {point.backupVaultName || "—"}
                    {airGapped && (
                      <span className="state-badge state-online" style={{ marginLeft: "0.5rem" }}>
                        🔒 {t("rpVaultAirgapped")}
                      </span>
                    )}
                    {selectedShared !== null && point.ownerAccountId && (
                      <div style={SMALL_TEXT_STYLE}>
                        {t("rpVaultOwner")}: {point.ownerAccountId}
                      </div>
                    )}
                    {regions.length > 1 && point.region && (
                      <div style={SMALL_TEXT_STYLE}>
                        {t("rpRegionLabel")}: {point.region}
                      </div>
                    )}
                  </td>
                  <td>{point.isEncrypted ? t("rpEncrypted") : t("rpNotEncrypted")}</td>
                  {isStorageAdmin === true && (
                    <td>
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={!RESTORABLE_STATUSES.has(point.status) || inOtherRegion}
                        onClick={() => {
                          setRestoreError(null);
                          setRestoreResult(null);
                          setPendingRestore(point);
                        }}
                      >
                        {t("rpRestore")}
                      </button>
                      {inOtherRegion && (
                        <div style={SMALL_TEXT_STYLE}>
                          {homeRegion ? t("rpRestoreOtherRegion").split("{region}").join(homeRegion) : t("rpRestoreRegionUnknown")}
                        </div>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="empty-state">{needsVaultChoice ? t("rpSelectVault") : t("rpEmpty")}</p>
      )}

      <p className="status-subtitle" style={{ display: "block", marginTop: "1rem" }}>
        {t("rpMonitoringNote")}{" "}
        <a href={observabilityHref} target="_blank" rel="noopener noreferrer" style={{ color: "var(--color-primary-text)" }}>
          📖 {t("rpMonitoringLink")}
        </a>
      </p>
    </div>
  );
}
