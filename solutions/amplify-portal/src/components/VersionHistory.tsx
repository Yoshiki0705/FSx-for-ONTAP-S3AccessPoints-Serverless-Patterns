import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";
import { errorMessage } from "../lib/portalQuery";
import { parseResponse } from "../utils/parseResponse";

const client = generateClient<Schema>();

// Parse the JSON string response from generic dispatch endpoints

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
export function VersionHistory({ mode = "browse" }: { mode?: "browse" | "diff" }) {

  const [lockDialog, setLockDialog] = useState<{ snapshotId: string } | null>(null);
  const [lockDays, setLockDays] = useState("30");
  const [lockLoading, setLockLoading] = useState(false);
  const [lockResult, setLockResult] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "tamperproof" | "scheduled" | "arp" | "manual">("all");
  const { t } = useTranslation();

  const {
    data,
    isFetching: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["protection", "listSnapshots"],
    queryFn: async () => {
      const response = await client.queries.protectionQuery({
        action: "listSnapshots",
        params: JSON.stringify({ maxResults: 20 }),
      });
      // `unknown`, not `any`: this resolver has been seen to return the snapshot list
      // either as an array or as a JSON string that needs a second parse, which the
      // branch below handles. `unknown` states that without disabling the checks that
      // make the branch necessary.
      const parsed = parseResponse<{
        snapshots?: unknown;
        volumeName?: string;
        error?: string;
      }>(response);
      if (!parsed) {
        if (response.errors?.length) {
          throw new Error(response.errors.map((e) => e.message).join(", "));
        }
        return { snapshots: [] as Snapshot[], volumeName: "" };
      }
      if (parsed.error) throw new Error(parsed.error);

      const raw = parsed.snapshots;
      const snapshots = ((): Snapshot[] => {
        if (typeof raw !== "string") return (raw ?? []) as Snapshot[];
        try {
          return JSON.parse(raw) as Snapshot[];
        } catch {
          return [];
        }
      })();
      return { snapshots, volumeName: parsed.volumeName ?? "" };
    },
  });

  const snapshots = data?.snapshots ?? [];
  const volumeName = data?.volumeName ?? "";

  // The lock dialog reports through lockResult, so a failed lock never shows up
  // here as a failed load.
  const loadSnapshots = () => void refetch();
  const error = errorMessage(queryError, "Failed to load snapshots");

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
      const response = await client.mutations.protectionMutation({ action: "lockSnapshot", params: JSON.stringify({
        snapshotId: lockDialog.snapshotId,
        expiryTime,
      }) });

      const data = parseResponse<{ success?: boolean; error?: string; expiryTime?: string }>(response);
      if (data) {
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
      {mode === "diff" && (
        <div className="version-diff-notice" style={{ padding: "1rem", background: "#fffbeb", border: "1px solid #fbbf24", borderRadius: "8px", marginBottom: "1rem" }}>
          <strong>🔄 {t("vhDiffTitle")}</strong>
          <p style={{ margin: "0.25rem 0 0", fontSize: "0.85rem", color: "#78350f" }}>
            {t("vhDiffNotice")}
          </p>
        </div>
      )}
      <div className="version-history-header">
        <h3>{t("snapshotsTitle")}</h3>
        {volumeName && (
          <span className="volume-badge" title={t("srcVolumeTitle")}>
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
          <div className="snapshot-filter-tabs" role="tablist" aria-label={t("vhSnapshotFilterAria")}>
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

          <table className="snapshot-table" role="grid" aria-label={t("vhVolumeSnapshotsAria")}>
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
                    <span className="lock-badge unlocked" title={t("vhNotLockedTitle")}>
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
                      alert(`FlexClone + S3 AP browse for "${snap.name}" — requires ONTAP VPC connection`);
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
