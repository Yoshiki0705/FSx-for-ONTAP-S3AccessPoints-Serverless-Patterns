import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { adminMutate, adminQuery } from "../../lib/dispatch";
import type { VolumeUuid } from "../../lib/dispatchActions";
import { SnaplockConfirmDialog } from "../SnaplockConfirmDialog";
import { VolumeSelector } from "./VolumeSelector";
import type { SnaplockIntent } from "../../utils/snaplockConsequences";

interface ExpiredEntry {
  resourceType: "volume" | "snapshot";
  volumeName: string;
  snapshotName?: string;
  snaplockType?: string;
  expiryTime: string;
}

interface SnaplockConfig {
  volumeName: string;
  type: string;
  isEnabled: boolean;
  complianceClockTime: string | null;
  retentionDefault: string | null;
  retentionMinimum: string | null;
  retentionMaximum: string | null;
  autocommitPeriod: string | null;
}

/**
 * SnapLock Manager — View SnapLock configuration and update retention.
 * System Manager-style: volume-level WORM settings display + retention update form.
 */
export function SnaplockManager() {
  const { t } = useTranslation();
  const [config, setConfig] = useState<SnaplockConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [volumeInput, setVolumeInput] = useState("");
  const [retentionDays, setRetentionDays] = useState(30);
  /** Set while the consequence dialog is open; null when nothing is pending. */
  const [pendingSnaplock, setPendingSnaplock] = useState<SnaplockIntent | null>(null);

  // Read-only view of locked resources whose retention has passed (expired) or
  // not yet (pending). This panel only shows them -- the deletion that would
  // follow is irreversible and is deliberately not offered here, so the boundary
  // that SnapLock retention is never shortened or bypassed stays intact.
  const { data: expiredData } = useQuery({
    queryKey: ["admin", "listExpiredRetention"],
    queryFn: async () => {
      const parsed = await adminQuery<{
        expired?: ExpiredEntry[];
        pending?: ExpiredEntry[];
        complianceClockTime?: string | null;
        clockSource?: string;
      }>({ action: "listExpiredRetention" });
      if (parsed?.error && !parsed.error.includes("Unknown action") && !parsed.error.includes("not configured")) {
        throw new Error(parsed.error);
      }
      return parsed;
    },
  });

  const loadConfig = async (volumeName?: string) => {
    const name = volumeName || volumeInput;
    if (!name) return;  // Don't call API without a volume name
    setLoading(true); setError(null);
    try {
      const data = await adminQuery<{ config?: SnaplockConfig }>({
        action: "getSnaplockConfig",
        params: { volumeName: volumeName || volumeInput || undefined },
      });
      if (data) {
        if (data.error) setError(data.error);
        else setConfig(data.config || null);
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Load failed"); }
    finally { setLoading(false); }
  };

  /**
   * Raising the default retention changes how long files committed from now on
   * stay undeletable, and an unexpired WORM file blocks the SVM and file system
   * as well. The dialog states that before the change is sent.
   */
  const handleUpdateRetentionClick = () => {
    if (!config || retentionDays <= 0) return;
    setError(null);
    setPendingSnaplock({
      kind: "updateSnaplockRetention",
      volumeName: config.volumeName,
      retentionDefault: `P${retentionDays}D`,
    });
  };

  const handleUpdateRetention = async () => {
    if (!config || retentionDays <= 0) return;
    // Need volume UUID — fetch it
    try {
      // `uuid` is branded here, where ONTAP's answer arrives, so that the update
      // below cannot be handed the volume *name* that sits beside it.
      const volData = await adminQuery<{ volumes?: { name: string; uuid: VolumeUuid }[] }>({
        action: "listVolumes",
      });
      if (volData) {
        const vol = (volData.volumes || []).find(v => v.name === config.volumeName);
        if (!vol) { setError(`Volume UUID not found for ${config.volumeName}`); return; }

        const data = await adminMutate<{ success?: boolean }>({
          action: "updateSnaplockRetention",
          params: { volumeUuid: vol.uuid, days: retentionDays, acknowledgeIrreversible: true },
        });
        if (data) {
          if (data.success) {
            setResult(`${t("rmRetentionUpdated")}: ${retentionDays} ${t("rmDays")}`);
            loadConfig(config.volumeName);
          } else setError(data.error || "Failed");
        }
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };

  return (
    <div className="admin-panel">
      {pendingSnaplock && (
        <SnaplockConfirmDialog
          intent={pendingSnaplock}
          onCancel={() => setPendingSnaplock(null)}
          onConfirm={() => {
            setPendingSnaplock(null);
            void handleUpdateRetention();
          }}
        />
      )}
      <div className="panel-header">
        <h3>{t("rmSnaplock")}</h3>
      </div>

      {error && <div className="error-message">{error}</div>}
      {result && <div className="success-message">{result}</div>}

      {/* Retention status across the SVM — read-only. Deleting an expired lock is
          irreversible and is not offered from here; this only surfaces what has
          passed its retention so an operator can plan removal elsewhere. */}
      {expiredData && ((expiredData.expired?.length ?? 0) > 0 || (expiredData.pending?.length ?? 0) > 0) && (
        <div className="rm-form" style={{ marginBottom: "1.5rem" }}>
          <h4>{t("slExpiredTitle")}</h4>
          <p className="rm-hint">
            {t("slExpiredClock")}: {expiredData.complianceClockTime
              ? new Date(expiredData.complianceClockTime).toLocaleString()
              : t("slExpiredNoClock")}
          </p>
          <p className="rm-hint">{t("slExpiredReadOnly")}</p>
          <table className="rm-table">
            <thead><tr>
              <th>{t("slExpiredStatus")}</th><th>{t("slExpiredResource")}</th>
              <th>{t("rmVolumeName")}</th><th>{t("slExpiredExpiry")}</th>
            </tr></thead>
            <tbody>
              {[
                ...(expiredData.expired ?? []).map(e => ({ ...e, status: "expired" as const })),
                ...(expiredData.pending ?? []).map(e => ({ ...e, status: "pending" as const })),
              ].map((e, i) => (
                <tr key={i}>
                  <td>
                    <span className={`lu-badge ${e.status === "expired" ? "disabled" : "active"}`}>
                      {e.status === "expired" ? t("slExpiredPast") : t("slExpiredPendingWord")}
                    </span>
                  </td>
                  <td>{e.resourceType === "snapshot" ? `${t("slExpiredSnapshot")}: ${e.snapshotName}` : t("slExpiredVolume")}</td>
                  <td className="lu-username">{e.volumeName}</td>
                  <td>{e.expiryTime ? new Date(e.expiryTime).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Volume lookup */}
      <div className="create-form" style={{ marginBottom: "1.5rem" }}>
        <VolumeSelector
          label={t("rmVolumeName")}
          onSelect={(vol) => {
            setError(null);
            // null means the SVM changed under the pick. Nothing is loaded for it: the
            // panel configures retention by volume name, and this one is irreversible
            // on the wrong volume.
            setVolumeInput(vol?.name ?? "");
            if (vol) loadConfig(vol.name);
          }}
          autoSelectFirst
          excludeFlexCache
        />
      </div>

      {loading && <p className="loading">{t("loading")}</p>}

      {config && (
        <div className="snaplock-details">
          <div className="detail-grid">
            <div className="detail-card">
              <div className="detail-label">{t("rmSnaplockType")}</div>
              <div className={`detail-value ${config.isEnabled ? "text-success" : ""}`}>
                {config.type === "compliance" ? "🔒 Compliance" :
                 config.type === "enterprise" ? "🔐 Enterprise" : "— Not configured"}
              </div>
            </div>
            <div className="detail-card">
              <div className="detail-label">{t("rmRetentionDefault")}</div>
              <div className="detail-value">{config.retentionDefault || "—"}</div>
            </div>
            <div className="detail-card">
              <div className="detail-label">{t("rmRetentionMin")}</div>
              <div className="detail-value">{config.retentionMinimum || "—"}</div>
            </div>
            <div className="detail-card">
              <div className="detail-label">{t("rmRetentionMax")}</div>
              <div className="detail-value">{config.retentionMaximum || "—"}</div>
            </div>
            <div className="detail-card">
              <div className="detail-label">{t("rmAutocommit")}</div>
              <div className="detail-value">{config.autocommitPeriod || "—"}</div>
            </div>
            <div className="detail-card">
              <div className="detail-label">{t("rmComplianceClock")}</div>
              <div className="detail-value">{config.complianceClockTime ? new Date(config.complianceClockTime).toLocaleString() : "—"}</div>
            </div>
          </div>

          {!config.isEnabled && (
            <div className="info-message" style={{ marginTop: "1rem" }}>
              <strong>ℹ️ {t("slNewVolumeOnly")}</strong>
              <p style={{ margin: "0.5rem 0 0", fontSize: "0.85rem", color: "var(--color-text-secondary)" }}>
                {t("slNewVolumeOnlyWhy")} {t("slNewVolumeOnlyHow")}
              </p>
            </div>
          )}

          {/* Update retention */}
          {config.isEnabled && (
            <div className="create-form" style={{ marginTop: "1.5rem" }}>
              <h4>{t("rmUpdateRetention")}</h4>
              <div className="form-row">
                <div className="form-group">
                  <label>{t("rmNewRetentionDays")}</label>
                  <input type="number" value={retentionDays} onChange={(e) => setRetentionDays(parseInt(e.target.value))}
                    min={1} max={36500} />
                  <small>{t("rmRetentionHint")}</small>
                </div>
                <button onClick={handleUpdateRetentionClick} className="btn-primary">{t("rmApply")}</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
