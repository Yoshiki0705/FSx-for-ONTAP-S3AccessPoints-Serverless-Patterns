import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
  isEncrypted: boolean;
  encryptionKeyArn: string;
  backupSizeInBytes: number;
}

interface BackupVault {
  backupVaultName: string;
  backupVaultArn: string;
  vaultType: string;
  locked: boolean;
  numberOfRecoveryPoints: number;
}

const LOGICALLY_AIR_GAPPED = "LOGICALLY_AIR_GAPPED_BACKUP_VAULT";

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
 * Recovery points — read-only list of AWS Backup recovery points (#459).
 *
 * Deliberately distinct from the "ONTAP Snapshots" panel: a cloud header, an
 * explicit sub-line stating these are AWS Backup points, and a vault-type chip for
 * logically air-gapped vaults. No restore action (that is #460) and no
 * cross-account selector (that is #461). No malware-scan column: FSx for ONTAP is
 * out of scope for Malware Protection for AWS Backup, so a same-named column would
 * mislead.
 */
export function RecoveryPoints() {
  const { t } = useTranslation();
  const isStorageAdmin = useStorageAdmin();
  const [statusFilter, setStatusFilter] = useState("");
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

  const pointsQuery = useQuery({
    queryKey: ["recoveryPoints", "listRecoveryPoints"],
    queryFn: () =>
      recoveryPointsQuery<{ recoveryPoints?: RecoveryPoint[] }>({
        action: "listRecoveryPoints",
        params: { maxResults: 100 },
      }),
  });

  const vaultsQuery = useQuery({
    queryKey: ["recoveryPoints", "listBackupVaults"],
    queryFn: () => recoveryPointsQuery<{ backupVaults?: BackupVault[] }>({ action: "listBackupVaults" }),
  });

  const points = pointsQuery.data?.recoveryPoints ?? [];
  const vaults = vaultsQuery.data?.backupVaults ?? [];
  const vaultByName = new Map(vaults.map((v) => [v.backupVaultName, v]));
  const loadError = errorMessage(pointsQuery.error, "") ?? pointsQuery.data?.error ?? null;

  const visiblePoints = statusFilter ? points.filter((p) => p.status === statusFilter) : points;
  const statuses = Array.from(new Set(points.map((p) => p.status))).filter(Boolean).sort();

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
        {point.statusMessage && (
          <div style={{ fontSize: "0.8rem", color: "var(--color-text-secondary)" }}>{point.statusMessage}</div>
        )}
      </>
    );
  };

  if (pointsQuery.isPending) {
    return (
      <div className="protection-section">
        <h2>☁️ {t("rpTitle")}</h2>
        <p className="loading">{t("loading")}</p>
      </div>
    );
  }

  return (
    <div className="protection-section">
      <div className="protection-header">
        <h2>☁️ {t("rpTitle")}</h2>
        <button onClick={() => void pointsQuery.refetch()} className="refresh-btn" aria-label={t("refresh")}>
          ↻
        </button>
      </div>
      <p className="status-subtitle" style={{ display: "block", marginBottom: "1rem" }}>
        {t("rpSubtitle")}
      </p>

      {loadError && <div className="error-message">{t("rpLoadError")}: {loadError}</div>}
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

      {visiblePoints.length > 0 ? (
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
              const airGapped = vault?.vaultType === LOGICALLY_AIR_GAPPED;
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
                  </td>
                  <td>{point.isEncrypted ? t("rpEncrypted") : t("rpNotEncrypted")}</td>
                  {isStorageAdmin === true && (
                    <td>
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={!RESTORABLE_STATUSES.has(point.status)}
                        onClick={() => {
                          setRestoreError(null);
                          setRestoreResult(null);
                          setPendingRestore(point);
                        }}
                      >
                        {t("rpRestore")}
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="empty-state">{t("rpEmpty")}</p>
      )}
    </div>
  );
}
