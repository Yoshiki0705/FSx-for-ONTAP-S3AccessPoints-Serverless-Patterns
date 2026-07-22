import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

interface Snapshot {
  name: string;
  createTime: string | null;
  snapshotId: string | null;
  state: string | null;
  comment: string | null;
  expiryTime: string | null;
  snaplockExpiryTime: string | null;
  isLocked: boolean;
}

/**
 * Version History component.
 *
 * Displays ONTAP snapshots for the current volume, enabling users to:
 * 1. See when snapshots were taken (point-in-time history)
 * 2. Trigger a FlexClone restore from a selected snapshot
 * 3. Browse past file states (via FlexClone + S3 AP)
 *
 * Architecture:
 *   AppSync query → VPC Lambda → ONTAP REST API → Snapshot list
 *
 * Note: Snapshot access requires ONTAP management LIF connectivity.
 * If ONTAP is not configured, this component shows an info message.
 */
export function VersionHistory() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [volumeName, setVolumeName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lockDialog, setLockDialog] = useState<{ snapshotId: string } | null>(null);
  const [lockDays, setLockDays] = useState("30");
  const [lockLoading, setLockLoading] = useState(false);
  const [lockResult, setLockResult] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "tamperproof" | "scheduled" | "arp" | "manual">("all");
  const { t } = useTranslation();

  const loadSnapshots = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await client.queries.listSnapshots({
        maxResults: 20,
      });

      if (response.data) {
        const snapshotData = response.data.snapshots;
        if (typeof snapshotData === "string") {
          try {
            setSnapshots(JSON.parse(snapshotData) as Snapshot[]);
          } catch {
            setSnapshots([]);
          }
        } else {
          setSnapshots((snapshotData || []) as Snapshot[]);
        }
        setVolumeName(response.data.volumeName || "");
        if (response.data.error) {
          setError(response.data.error);
        }
      } else if (response.errors) {
        setError(response.errors.map((e) => e.message).join(", "));
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load snapshots";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSnapshots();
  }, []);

  const formatDate = (isoString: string | null) => {
    if (!isoString) return "—";
    try {
      return new Date(isoString).toLocaleString();
    } catch {
      return isoString;
    }
  };

  const handleLockSnapshot = (snapshotId: string) => {
    setLockDialog({ snapshotId });
    setLockResult(null);
  };

  const submitLock = async () => {
    if (!lockDialog) return;
    setLockLoading(true);
    setLockResult(null);

    const days = parseInt(lockDays, 10);
    if (isNaN(days) || days < 1 || days > 365) {
      setLockResult("Error: Enter a value between 1 and 365 days");
      setLockLoading(false);
      return;
    }

    // Calculate expiry_time as ISO 8601
    const expiry = new Date();
    expiry.setDate(expiry.getDate() + days);
    const expiryTime = expiry.toISOString();

    try {
      const response = await client.mutations.lockSnapshot({
        snapshotId: lockDialog.snapshotId,
        expiryTime,
      });

      if (response.data) {
        const data = response.data as { success?: boolean; error?: string; expiryTime?: string };
        if (data.success) {
          setLockResult(`Snapshot locked until ${expiryTime}`);
          setLockDialog(null);
          // Refresh to show updated lock status
          loadSnapshots();
        } else {
          setLockResult(`Error: ${data.error || "Lock failed"}`);
        }
      } else if (response.errors) {
        setLockResult(`Error: ${response.errors.map((e) => e.message).join(", ")}`);
      }
    } catch (err) {
      setLockResult(`Error: ${err instanceof Error ? err.message : "Lock failed"}`);
    } finally {
      setLockLoading(false);
    }
  };

  const getSnapshotType = (name: string): string => {
    if (name.startsWith("daily.")) return "Daily";
    if (name.startsWith("hourly.")) return "Hourly";
    if (name.startsWith("weekly.")) return "Weekly";
    if (name.startsWith("snapmirror.")) return "SnapMirror";
    if (name.startsWith("Anti_ransomware_backup")) return "ARP";
    return "Manual";
  };

  const getFilteredSnapshots = (): Snapshot[] => {
    switch (filter) {
      case "tamperproof":
        return snapshots.filter((s) => s.isLocked);
      case "scheduled":
        return snapshots.filter((s) => {
          const type = getSnapshotType(s.name);
          return type === "Daily" || type === "Hourly" || type === "Weekly";
        });
      case "arp":
        return snapshots.filter((s) => getSnapshotType(s.name) === "ARP");
      case "manual":
        return snapshots.filter((s) => {
          const type = getSnapshotType(s.name);
          return type === "Manual";
        });
      default:
        return snapshots;
    }
  };

  const filteredSnapshots = getFilteredSnapshots();
  const tamperproofCount = snapshots.filter((s) => s.isLocked).length;
  const arpCount = snapshots.filter((s) => getSnapshotType(s.name) === "ARP").length;

  return (
    <div className="version-history">
      <div className="version-history-header">
        <h3>{t("snapshotsTitle")}</h3>
        {volumeName && (
          <span className="volume-badge" title="Source volume">
            {t("snapshotsVolumeLabel")}: {volumeName}
          </span>
        )}
        <button
          onClick={loadSnapshots}
          disabled={loading}
          className="refresh-btn"
          title={t("snapshotsRefreshTitle")}
        >
          {loading ? t("snapshotsLoadingBtn") : t("snapshotsRefreshBtn")}
        </button>
      </div>

      {error && (
        <div className="protection-section" style={{ marginTop: "1rem" }}>
          <div className="protection-info">
            <h3>{t("snapshotsOntapRequiredTitle")}</h3>
            <p>{t("snapshotsOntapRequiredDesc")}</p>
            <ul>
              <li>{t("snapshotsOntapRequiredDetail1")}</li>
              <li>{t("envVarsRequired")}: <code>ONTAP_MGMT_IP</code>, <code>ONTAP_SECRET_NAME</code>, <code>VOLUME_NAME</code>, <code>SVM_NAME</code></li>
              <li>{t("snapshotsOntapRequiredDetail2")}</li>
            </ul>
            <p className="integration-note">
              <strong>{t("demoModeNote")}</strong>: {t("arpDemoModeNote")}
            </p>
            <details>
              <summary>{t("errorDetails")}</summary>
              <pre style={{ fontSize: "0.8rem", overflow: "auto", padding: "0.5rem", background: "#f5f5f5", borderRadius: "4px" }}>{error}</pre>
            </details>
          </div>
        </div>
      )}

      {!error && snapshots.length === 0 && !loading && (
        <p className="empty-state">{t("snapshotsEmpty")}</p>
      )}

      {snapshots.length > 0 && (
        <>
          {/* Filter tabs — separate Tamperproof from regular */}
          <div className="snapshot-filter-tabs" role="tablist" aria-label="Snapshot filter">
            <button
              role="tab"
              aria-selected={filter === "all"}
              className={`filter-tab ${filter === "all" ? "active" : ""}`}
              onClick={() => setFilter("all")}
            >
              {t("snapshotsFilterAll")} ({snapshots.length})
            </button>
            <button
              role="tab"
              aria-selected={filter === "tamperproof"}
              className={`filter-tab ${filter === "tamperproof" ? "active" : ""}`}
              onClick={() => setFilter("tamperproof")}
            >
              {t("snapshotsFilterTamperproof")} ({tamperproofCount})
            </button>
            <button
              role="tab"
              aria-selected={filter === "scheduled"}
              className={`filter-tab ${filter === "scheduled" ? "active" : ""}`}
              onClick={() => setFilter("scheduled")}
            >
              {t("snapshotsFilterScheduled")}
            </button>
            <button
              role="tab"
              aria-selected={filter === "arp"}
              className={`filter-tab ${filter === "arp" ? "active" : ""}`}
              onClick={() => setFilter("arp")}
            >
              {t("snapshotsFilterArp")} ({arpCount})
            </button>
            <button
              role="tab"
              aria-selected={filter === "manual"}
              className={`filter-tab ${filter === "manual" ? "active" : ""}`}
              onClick={() => setFilter("manual")}
            >
              {t("snapshotsFilterManual")}
            </button>
          </div>

          <table className="snapshot-table" role="grid" aria-label="Volume snapshots">
          <thead>
            <tr>
              <th scope="col">{t("snapshotsColName")}</th>
              <th scope="col">{t("snapshotsColType")}</th>
              <th scope="col">{t("snapshotsColCreated")}</th>
              <th scope="col">{t("snapshotsColLock")}</th>
              <th scope="col">{t("snapshotsColState")}</th>
              <th scope="col">{t("snapshotsColActions")}</th>
            </tr>
          </thead>
          <tbody>
            {filteredSnapshots.map((snap) => (
              <tr key={snap.snapshotId || snap.name} className={snap.isLocked ? "row-locked" : ""}>
                <td className="snapshot-name" title={snap.comment || undefined}>
                  {snap.name}
                </td>
                <td>
                  <span className={`type-badge type-${getSnapshotType(snap.name).toLowerCase()}`}>
                    {getSnapshotType(snap.name)}
                  </span>
                </td>
                <td>{formatDate(snap.createTime)}</td>
                <td>
                  {snap.isLocked ? (
                    <span className="lock-badge locked" title={`Locked until: ${snap.expiryTime || snap.snaplockExpiryTime || "unknown"}`}>
                      🔐 {snap.expiryTime ? formatDate(snap.expiryTime) : "Locked"}
                    </span>
                  ) : (
                    <span className="lock-badge unlocked" title="Not locked — can be deleted">
                      🔓
                    </span>
                  )}
                </td>
                <td>
                  <span className={`state-badge state-${snap.state}`}>
                    {snap.state || "valid"}
                  </span>
                </td>
                <td className="action-cell">
                  <button
                    className="action-btn"
                    title={t("snapshotsBrowseBtn")}
                    onClick={() => {
                      window.dispatchEvent(
                        new CustomEvent("restore-snapshot", {
                          detail: { snapshotName: snap.name },
                        })
                      );
                    }}
                  >
                    {t("snapshotsBrowseBtn")}
                  </button>
                  {!snap.isLocked && snap.snapshotId && (
                    <button
                      className="action-btn lock-btn"
                      title={t("snapshotsLockBtn")}
                      onClick={() => handleLockSnapshot(snap.snapshotId!)}
                    >
                      {t("snapshotsLockBtn")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </>
      )}

      {lockResult && (
        <div className={lockResult.startsWith("Error") ? "error-message" : "success-message"}>
          {lockResult}
        </div>
      )}

      {lockDialog && (
        <div className="lock-dialog" role="dialog" aria-labelledby="lock-dialog-title">
          <div className="dialog-content">
            <h3 id="lock-dialog-title">{t("snapshotsLockDialogTitle")}</h3>
            <p className="dialog-description">{t("snapshotsLockDialogDesc")}</p>
            <div className="dialog-field">
              <label htmlFor="lock-days">{t("snapshotsLockDaysLabel")}</label>
              <input
                id="lock-days"
                type="number"
                min="1"
                max="365"
                value={lockDays}
                onChange={(e) => setLockDays(e.target.value)}
                disabled={lockLoading}
              />
              <small>{t("snapshotsLockDaysHint")}</small>
            </div>
            <div className="dialog-actions">
              <button
                className="action-btn lock-confirm-btn"
                onClick={submitLock}
                disabled={lockLoading}
              >
                {lockLoading ? t("snapshotsLocking") : t("snapshotsLockConfirmBtn")}
              </button>
              <button
                className="action-btn cancel-btn"
                onClick={() => setLockDialog(null)}
                disabled={lockLoading}
              >
                {t("cancel")}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="version-history-footer">
        <small>{t("snapshotsFooterNote")}</small>
      </div>
    </div>
  );
}
