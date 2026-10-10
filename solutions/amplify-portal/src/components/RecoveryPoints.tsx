import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../i18n";
import type { TranslationKeys } from "../i18n/locales/ja";
import { errorMessage } from "../lib/portalQuery";
import { recoveryPointsQuery } from "../lib/dispatch";

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
  const [statusFilter, setStatusFilter] = useState("");

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
