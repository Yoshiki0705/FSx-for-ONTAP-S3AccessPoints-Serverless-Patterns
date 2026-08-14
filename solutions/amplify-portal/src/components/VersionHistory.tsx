import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../i18n";
import {
  DispatchError,
  errorMessage,
  failureDiagnosis,
  type FailureDiagnosis,
} from "../lib/portalQuery";
import { dispatch } from "../lib/dispatch";
import { daysFromNow, type SnapshotId } from "../lib/dispatchActions";
import { useActiveSvm } from "../hooks/useActiveSvm";
import { useStorageAdmin } from "../hooks/useStorageAdmin";
import { OntapFailureNotice } from "./OntapFailureNotice";
import { SnaplockConfirmDialog } from "./SnaplockConfirmDialog";
import { VolumeScopeBadge } from "./VolumeScopeBadge";
import { SvmSelector } from "./admin/SvmSelector";
import { VolumeSelector } from "./admin/VolumeSelector";
import { parseResponse } from "../utils/parseResponse";
import type { SnaplockIntent } from "../utils/snaplockConsequences";

interface Snapshot {
  name: string;
  createTime: string | null;
  /** ONTAP's UUID for the snapshot, branded where it arrives. */
  snapshotId: SnapshotId | null;
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

  const [lockDialog, setLockDialog] = useState<{ snapshotId: SnapshotId } | null>(null);
  const [lockDays, setLockDays] = useState("30");
  const [lockLoading, setLockLoading] = useState(false);
  const [lockResult, setLockResult] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "tamperproof" | "scheduled" | "arp" | "manual">("all");
  /** Set while the consequence dialog is open; null when nothing is pending. */
  const [pendingSnaplock, setPendingSnaplock] = useState<SnaplockIntent | null>(null);
  const { t } = useTranslation();
  const isStorageAdmin = useStorageAdmin();
  // Which volume's history this is. Empty means the configured one, which is the
  // handler's fallback and what a reader outside the storage-admin group gets. Until
  // this existed the page could only ever show that one volume, so snapshots taken
  // anywhere else looked like snapshots that had not been taken.
  const [selectedVolume, setSelectedVolume] = useState("");
  // See ArpStatus: a volume name means nothing outside its SVM, and here it also
  // decides which volume a lock lands on -- a lock that cannot be undone.
  const activeSvm = useActiveSvm();
  const [svmAtSelection, setSvmAtSelection] = useState(activeSvm);
  const volumeInScope = svmAtSelection === activeSvm ? selectedVolume : "";

  const {
    data,
    isFetching: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["protection", "listSnapshots", activeSvm || null, volumeInScope || null],
    queryFn: async () => {
      const response = await dispatch("protectionQuery", {
        action: "listSnapshots",
        // `svm` is added by dispatch from the active scope; the volume is this
        // page's part.
        params: volumeInScope
          ? { maxResults: 20, volumeName: volumeInScope }
          : { maxResults: 20 },
      });
      // `unknown`, not `any`: this resolver has been seen to return the snapshot list
      // either as an array or as a JSON string that needs a second parse, which the
      // branch below handles. `unknown` states that without disabling the checks that
      // make the branch necessary.
      const parsed = parseResponse<
        {
          snapshots?: unknown;
          volumeName?: string;
          error?: string;
        } & FailureDiagnosis
      >(response);
      if (!parsed) {
        if (response.errors?.length) {
          throw new DispatchError(response.errors.map((e) => e.message).join(", "));
        }
        return { snapshots: [] as Snapshot[], volumeName: "" };
      }
      // DispatchError, not Error: the class of failure travels with the message so
      // the notice below can name the one cause instead of guessing at five.
      if (parsed.error) throw new DispatchError(parsed.error, parsed);

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

  const handleLockSnapshot = (snapshotId: SnapshotId) => {
    setLockDialog({ snapshotId });
    setLockResult(null);
  };

  /**
   * The day count is validated here, then the consequence dialog states the
   * resulting date and that the lock cannot be shortened or released. This
   * dialog only collects a number; it never said what the number does.
   */
  const submitLock = () => {
    if (!lockDialog) return;
    setLockResult(null);

    const days = parseInt(lockDays, 10);
    if (isNaN(days) || days < 1 || days > 365) {
      setLockResult("Error: Enter a value between 1 and 365 days");
      return;
    }

    setPendingSnaplock({
      kind: "lockSnapshot",
      snapshotName: lockDialog.snapshotId,
      retentionDays: days,
    });
  };

  const performLock = async () => {
    if (!lockDialog) return;
    setLockLoading(true);
    setLockResult(null);

    const days = parseInt(lockDays, 10);
    if (isNaN(days) || days < 1 || days > 365) {
      setLockResult("Error: Enter a value between 1 and 365 days");
      setLockLoading(false);
      return;
    }

    // An absolute instant, which is what the action reads. `daysFromNow` returns the
    // branded type, so a day count cannot reach the field by mistake.
    const expiryTime = daysFromNow(days);

    try {
      // `dispatch` rather than `protectionMutate` because the branch below reports
      // GraphQL-level errors, which only the raw response carries.
      const response = await dispatch("protectionMutation", {
        action: "lockSnapshot",
        params: {
          snapshotId: lockDialog.snapshotId,
          expiryTime,
          acknowledgeIrreversible: true,
          // The volume the listing came from. Without it the handler resolves the
          // configured volume and looks for this snapshot there, which on any other
          // volume is a lock applied to the wrong subject -- and locks do not come off.
          ...(volumeInScope ? { volumeName: volumeInScope } : {}),
        },
      });
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
      {pendingSnaplock && (
        <SnaplockConfirmDialog
          intent={pendingSnaplock}
          onCancel={() => setPendingSnaplock(null)}
          onConfirm={() => {
            setPendingSnaplock(null);
            void performLock();
          }}
        />
      )}
      {mode === "diff" && (
        <div className="version-diff-notice" style={{ padding: "1rem", background: "var(--color-warning-bg)", border: "1px solid var(--color-warning)", borderRadius: "8px", marginBottom: "1rem" }}>
          <strong>🔄 {t("vhDiffTitle")}</strong>
          <p style={{ margin: "0.25rem 0 0", fontSize: "0.85rem", color: "var(--color-warning-text)" }}>
            {t("vhDiffNotice")}
          </p>
        </div>
      )}
      <div className="version-history-header">
        <h3>{t("snapshotsTitle")}</h3>
        <VolumeScopeBadge volumeName={volumeName} isDefault={!volumeInScope} />
        <button
          onClick={loadSnapshots}
          disabled={loading}
          className="refresh-btn"
          title={t("snapshotsRefreshTitle")}
        >
          {loading ? t("snapshotsLoadingBtn") : t("snapshotsRefreshBtn")}
        </button>
      </div>

      {/* The scope, on a row of its own: file system (fixed by the connection) then SVM
          then volume. Filtering by volume alone does not scale past a handful of them,
          and a name is only unique within its SVM. */}
      {isStorageAdmin === true && (
        <div className="protection-scope">
          <SvmSelector />
          <span className="protection-scope-chain" aria-hidden="true">›</span>
          <VolumeSelector
            label={t("rmSelectVolume")}
            onSelect={(vol) => {
              setSelectedVolume(vol?.name ?? "");
              setSvmAtSelection(activeSvm);
            }}
          />
        </div>
      )}

      {error && <OntapFailureNotice error={error} {...failureDiagnosis(queryError)} />}

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
