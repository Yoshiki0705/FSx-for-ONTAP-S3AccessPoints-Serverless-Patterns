import { useState } from "react";
import { useTranslation } from "../../i18n";
import { adminMutate, adminQuery } from "../../lib/dispatch";
import type { VolumeUuid } from "../../lib/dispatchActions";
import { SnaplockConfirmDialog } from "../SnaplockConfirmDialog";
import { VolumeSelector } from "./VolumeSelector";
import type { SnaplockIntent } from "../../utils/snaplockConsequences";

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

      {/* Volume lookup */}
      <div className="create-form" style={{ marginBottom: "1.5rem" }}>
        <VolumeSelector
          label={t("rmVolumeName")}
          onSelect={(vol) => { setVolumeInput(vol.name); setError(null); loadConfig(vol.name); }}
          autoSelectFirst
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
              <p style={{ margin: "0.5rem 0 0", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
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
