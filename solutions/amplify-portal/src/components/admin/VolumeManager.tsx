import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage, unwrap } from "../../lib/portalQuery";
import { adminMutate, dispatch } from "../../lib/dispatch";
import { asIsoDuration, type IsoDuration, type VolumeUuid } from "../../lib/dispatchActions";
import { SnaplockConfirmDialog } from "../SnaplockConfirmDialog";
import { VolumeRebalancePanel } from "./VolumeRebalancePanel";
import { VolumeMountPanel } from "./VolumeMountPanel";
import { durationLabel, durationRange } from "../../utils/duration";
import { oneOf } from "../../utils/oneOf";
import type { SnaplockIntent } from "../../utils/snaplockConsequences";

interface Volume {
  name: string;
  /** ONTAP's UUID, branded where it arrives so the name beside it cannot stand in. */
  uuid: VolumeUuid;
  sizeBytes: number;
  sizeGiB: number;
  usedPercent: number;
  state: string;
  /** "flexvol" | "flexgroup". Decides which operations exist for the volume. */
  style: string;
  securityStyle: string;
  snaplockType: string;
  /**
   * Where the volume is mounted, or "" when it is not mounted at all.
   *
   * An unmounted volume is listed as online and is invisible to every NFS and SMB
   * client, so without this the row cannot distinguish reachable from orphaned --
   * and orphaned is what a refused delete leaves behind, since it unmounts first.
   */
  junctionPath: string;
  /** "none" | "cache" | "origin". A cache is always a FlexGroup. */
  flexcacheEndpointType: string;
  /** The active file system alone, with snapshots accounted for separately below. */
  afsUsedBytes: number;
  snapshotUsedBytes: number;
  snapshotReservePercent: number;
  snapshotReserveBytes: number;
  /** Snapshot data past the reserve, which competes with live data for the volume. */
  snapshotSpillBytes: number;
  snapshotAutodeleteEnabled: boolean;
}

const BYTES_PER_GIB = 1024 ** 3;

/**
 * A size with a unit that suits it.
 *
 * Snapshot usage and volume size differ by six orders of magnitude on the same
 * table -- 77 MiB of snapshots on a 2 TiB volume -- so a single unit either
 * rounds the small numbers to nothing or makes the large ones unreadable.
 */
/** ONTAP's own word, kept as ONTAP writes it rather than translated. */
function styleLabel(style: string): string {
  if (style === "flexgroup") return "FlexGroup";
  if (style === "flexvol") return "FlexVol";
  return style || "—";
}

/** Literal keys, so a typo here is a type error rather than a tooltip of raw key text. */
function styleTitleKey(style: string): "rmStyleFlexgroupTitle" | "rmStyleFlexvolTitle" {
  return style === "flexgroup" ? "rmStyleFlexgroupTitle" : "rmStyleFlexvolTitle";
}

/** The share of the volume held by live data, as a percentage of its size. */
function afsPercent(vol: Volume): number {
  return (vol.afsUsedBytes / Math.max(vol.sizeBytes, 1)) * 100;
}

/** The share held by snapshot data that no longer fits in the reserve. */
function spillPercent(vol: Volume): number {
  return (vol.snapshotSpillBytes / Math.max(vol.sizeBytes, 1)) * 100;
}

function capacityLabel(bytes: number): string {
  if (bytes <= 0) return "0";
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KiB`;
  if (bytes < BYTES_PER_GIB) return `${(bytes / 1024 ** 2).toFixed(1)} MiB`;
  if (bytes < 1024 ** 4) return `${(bytes / BYTES_PER_GIB).toFixed(1)} GiB`;
  return `${(bytes / 1024 ** 4).toFixed(2)} TiB`;
}

/**
 * Volume Manager — List, create, resize, delete volumes.
 * System Manager-style table with capacity bar + action buttons.
 */
export function VolumeManager() {
  const { t } = useTranslation();
  const [actionError, setActionError] = useState<string | null>(null);
  const setError = setActionError;
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [actionResult, setActionResult] = useState<string | null>(null);

  // Create form state
  const [newName, setNewName] = useState("");
  const [newSize, setNewSize] = useState(100);
  // Narrowed to the values ONTAP accepts. As bare strings a typo reached the API,
  // where `securityStyle: "unxi"` is a 400 and `snaplockType: "complaince"` quietly
  // produced a volume with no SnapLock at all.
  const [newStyle, setNewStyle] = useState<"unix" | "ntfs" | "mixed">("unix");
  const [newSnaplockType, setNewSnaplockType] = useState<"none" | "compliance" | "enterprise">("none");
  const [newRetentionDefault, setNewRetentionDefault] = useState("P30D");
  const [newRetentionMin, setNewRetentionMin] = useState("P1D");
  const [newRetentionMax, setNewRetentionMax] = useState("P365D");
  const [customRetentionNum, setCustomRetentionNum] = useState("30");
  const [customRetentionUnit, setCustomRetentionUnit] = useState("D");

  /** Set while the consequence dialog is open; null when nothing is pending. */
  const [pendingSnaplock, setPendingSnaplock] = useState<SnaplockIntent | null>(null);

  /** The FlexGroup whose rebalance panel is open, if any. */
  const [rebalancing, setRebalancing] = useState<{ uuid: VolumeUuid; name: string } | null>(null);

  /** The volume whose mount panel is open, if any. */
  const [mounting, setMounting] = useState<{ uuid: VolumeUuid; name: string } | null>(null);

  const {
    data: volumes = [],
    isPending: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "listVolumes"],
    queryFn: () =>
      unwrap<{ volumes?: Volume[] }>(dispatch("adminQuery", { action: "listVolumes" })).then(
        (d) => d?.volumes ?? [],
      ),
  });

  // Mutation handlers report through their own state, so a failed action is
  // never mistaken for a failed load.
  const loadVolumes = () => void refetch();
  const error = actionError ?? errorMessage(queryError, "Failed to load volumes");


  /** The retention default as it will be sent, resolving the custom row. */
  const resolvedRetentionDefault = () =>
    newRetentionDefault === "custom"
      ? `P${customRetentionNum}${customRetentionUnit}`
      : newRetentionDefault;

  /**
   * A SnapLock volume cannot be un-SnapLocked, and once it holds an unexpired
   * WORM file the SVM and file system stop being deletable too. So the create
   * button routes through the consequence dialog instead of submitting, and
   * only a plain volume submits directly.
   */
  const handleCreateClick = () => {
    if (!newName) { setError(t("rmVolumeNameRequired")); return; }
    if (newSnaplockType === "none") { void handleCreate(); return; }
    setError(null);
    setPendingSnaplock({
      kind: "createSnaplockVolume",
      volumeName: newName,
      snaplockType: newSnaplockType as "compliance" | "enterprise",
      retentionDefault: resolvedRetentionDefault(),
      retentionMax: newRetentionMax,
    });
  };

  const handleCreate = async () => {
    if (!newName) { setError(t("rmVolumeNameRequired")); return; }

    // The three retention fields are ISO 8601 periods, and one of them is assembled
    // from a number and a unit the operator picks. Validating them here means a
    // malformed period is refused before it becomes a volume that cannot be undone;
    // previously anything shaped like a string was sent.
    const snaplock = newSnaplockType === "none" ? null : newSnaplockType;
    let retention: { retentionDefault: IsoDuration; retentionMin: IsoDuration; retentionMax: IsoDuration } | null =
      null;
    if (snaplock) {
      const periods = [resolvedRetentionDefault(), newRetentionMin, newRetentionMax].map(asIsoDuration);
      const [asDefault, asMin, asMax] = periods;
      if (!asDefault || !asMin || !asMax) { setError(t("rmRetentionInvalid")); return; }
      retention = { retentionDefault: asDefault, retentionMin: asMin, retentionMax: asMax };
    }

    setActionResult(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "createVolume",
        params: {
          name: newName,
          sizeGiB: newSize,
          securityStyle: newStyle,
          ...(snaplock
            ? {
                snaplockType: snaplock,
                ...retention!,
                // The backend refuses SnapLock settings without this, so a caller
                // that bypasses the dialog cannot create a lock either.
                acknowledgeIrreversible: true as const,
              }
            : {}),
        },
      });
      if (data) {
        if (data.success) {
          setActionResult(`${t("rmVolumeCreated")}: ${newName}`);
          setShowCreateForm(false);
          setNewName(""); setNewSize(100);
          loadVolumes();
        } else setError(data.error || "Create failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Create failed"); }
  };

  const handleResize = async (uuid: VolumeUuid, name: string) => {
    const input = prompt(t("rmResizePrompt"), "200");
    if (!input) return;
    const newSizeGiB = parseInt(input, 10);
    if (isNaN(newSizeGiB) || newSizeGiB <= 0) { setError("Invalid size"); return; }
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "resizeVolume",
        params: { volumeUuid: uuid, newSizeGiB },
      });
      if (data) {
        if (data.success) { setActionResult(`${name} → ${newSizeGiB} GiB`); loadVolumes(); }
        else setError(data.error || "Resize failed");
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Resize failed"); }
  };

  const handleDelete = async (uuid: VolumeUuid, name: string) => {
    if (!confirm(t("rmDeleteConfirm").replace("{name}", name))) return;
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "deleteVolume",
        params: { volumeUuid: uuid, volumeName: name, confirm: true },
      });
      if (data) {
        if (data.success) { setActionResult(t("rmDeleted").replace("{name}", name)); loadVolumes(); }
        // Reloaded on failure too: the delete takes the volume offline first, so a
        // failed one leaves the row's state stale as well as the volume unusable.
        else {
          const message = data.error || "Delete failed";
          // ONTAP's own sentence names clones that the operator may have deleted minutes
          // ago, because a deleted volume sits in the recovery queue for 12 hours by
          // default and still counts as a clone from the parent's side. Measured: the
          // parent of an unsplit deleted clone was still refused, while the parent of a
          // split one deleted immediately. The way out is in the message rather than in
          // a document nobody is reading at that moment.
          setError(/one or more clones/i.test(message) ? `${message} — ${t("rmDeleteBlockedByCloneHint")}` : message);
          loadVolumes();
        }
      }
    } catch (err) { setError(err instanceof Error ? err.message : "Delete failed"); }
  };

  /** Reverse the offline step a failed delete left behind. */
  const handleBringOnline = async (uuid: VolumeUuid, name: string) => {
    setError(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "bringVolumeOnline",
        params: { volumeUuid: uuid, volumeName: name },
      });
      if (data?.success) {
        setActionResult(t("rmBroughtOnline").replace("{name}", name));
        loadVolumes();
      } else setError(data?.error || t("rmActionFailed"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("rmActionFailed"));
    }
  };

  if (loading) return <p className="loading">{t("loading")}</p>;

  return (
    <div className="admin-panel">
      {pendingSnaplock && (
        <SnaplockConfirmDialog
          intent={pendingSnaplock}
          onCancel={() => setPendingSnaplock(null)}
          onConfirm={() => {
            setPendingSnaplock(null);
            void handleCreate();
          }}
        />
      )}
      <div className="panel-header">
        <h3>{t("rmVolumes")}</h3>
        <div className="panel-actions">
          <button onClick={() => setShowCreateForm(!showCreateForm)} className="btn-primary">
            + {t("rmCreateVolume")}
          </button>
          <button onClick={loadVolumes} className="refresh-btn">↻</button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}
      {actionResult && <div className="success-message">{actionResult}</div>}

      {showCreateForm && (
        <div className="create-form">
          <div className="form-row">
            <div className="form-group">
              <label>{t("rmVolumeName")}</label>
              <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)}
                placeholder="my_volume_01" />
              <small>{t("rmVolumeNameHint")}</small>
            </div>
            <div className="form-group">
              <label>{t("rmVolumeSize")} (GiB)</label>
              <input type="number" value={newSize} onChange={(e) => setNewSize(parseInt(e.target.value))}
                min={1} max={196608} />
            </div>
            <div className="form-group">
              <label>{t("rmSecurityStyle")}</label>
              <select
                value={newStyle}
                onChange={(e) => setNewStyle(oneOf(["unix", "ntfs", "mixed"], e.target.value, "unix"))}
              >
                <option value="unix">UNIX</option>
                <option value="ntfs">NTFS</option>
                <option value="mixed">Mixed</option>
              </select>
            </div>
          </div>
          {/* SnapLock configuration (optional) */}
          <div className="form-row">
            <div className="form-group">
              <label>{t("rmSnaplockType")}</label>
              <select
                value={newSnaplockType}
                onChange={(e) =>
                  setNewSnaplockType(oneOf(["none", "enterprise", "compliance"], e.target.value, "none"))
                }
              >
                <option value="none">None (standard volume)</option>
                <option value="enterprise">Enterprise (privileged delete)</option>
                <option value="compliance">Compliance (immutable)</option>
              </select>
              <small>{t("rmSnaplockTypeHint")}</small>
            </div>
            {newSnaplockType !== "none" && (
              <>
                <div className="form-group">
                  <label>{t("rmSnaplockRetentionDefault")}</label>
                  <select value={newRetentionDefault} onChange={(e) => setNewRetentionDefault(e.target.value)}>
                    {["P1D", "P7D", "P30D", "P90D", "P180D", "P365D", "P730D", "P1825D", "P3650D", "custom"].map(
                      (period) => (
                        <option key={period} value={period}>{durationLabel(period, t)}</option>
                      )
                    )}
                  </select>
                  {newRetentionDefault === "custom" && (
                    <div className="form-row" style={{ marginTop: "0.3rem", gap: "0.5rem" }}>
                      <input type="number" value={customRetentionNum} onChange={(e) => setCustomRetentionNum(e.target.value)}
                        min={1} max={10950} style={{ width: "80px" }} />
                      <select value={customRetentionUnit} onChange={(e) => setCustomRetentionUnit(e.target.value)} style={{ width: "100px" }}>
                        <option value="D">{t("durationUnitDay")}</option>
                        <option value="M">{t("durationUnitMonth")}</option>
                        <option value="Y">{t("durationUnitYear")}</option>
                      </select>
                    </div>
                  )}
                  <small>{t("rmRetentionDefaultHint")} ({durationRange("P1D", "P10950D", t)})</small>
                </div>
                <div className="form-group">
                  <label>{t("rmSnaplockRetentionMin")}</label>
                  <select value={newRetentionMin} onChange={(e) => setNewRetentionMin(e.target.value)}>
                    {["P0D", "P1D", "P7D", "P30D", "P90D", "P365D"].map((period) => (
                      <option key={period} value={period}>{durationLabel(period, t)}</option>
                    ))}
                  </select>
                  <small>{durationRange("P0D", "P10950D", t)}</small>
                </div>
                <div className="form-group">
                  <label>{t("rmSnaplockRetentionMax")}</label>
                  <select value={newRetentionMax} onChange={(e) => setNewRetentionMax(e.target.value)}>
                    {["P30D", "P90D", "P365D", "P730D", "P1825D", "P3650D", "P10950D"].map((period) => (
                      <option key={period} value={period}>{durationLabel(period, t)}</option>
                    ))}
                  </select>
                  <small>{durationRange("P1D", "P10950D", t)}</small>
                </div>
                <div className="info-message" style={{ marginTop: "0.5rem" }}>
                  ⚠️ {t("rmSnaplockRetentionWarning")}
                  {" "}
                  <a href="https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/how-snaplock-works.html" target="_blank" rel="noopener noreferrer" style={{ color: "var(--color-primary-text)" }}>
                    📖 {t("rmSnaplockDocs")}
                  </a>
                </div>
              </>
            )}
          </div>
          <button onClick={handleCreateClick} className="btn-primary">{t("rmCreate")}</button>
          <button onClick={() => setShowCreateForm(false)} className="btn-secondary">{t("cancel")}</button>
        </div>
      )}

      {/* Two behaviours this table shows numbers for without explaining them: what a
          volume's used figure does and does not count, and what its style decides.
          Collapsed, because most visits are not asking. */}
      <details className="rm-guide">
        <summary>{t("rmCapacityGuideTitle")}</summary>

        <p className="fc-split-heading">{t("rmCapacityGuideWhyTitle")}</p>
        <ul>
          <li>{t("rmCapacityGuideWhy1")}</li>
          <li>{t("rmCapacityGuideWhy2")}</li>
          <li>{t("rmCapacityGuideWhy3")}</li>
          <li>{t("rmCapacityGuideWhy4")}</li>
          <li>{t("rmCapacityGuideWhy5")}</li>
        </ul>

        <p className="fc-split-heading">{t("rmCapacityGuideActTitle")}</p>
        <ul>
          <li>{t("rmCapacityGuideAct1")}</li>
          <li>{t("rmCapacityGuideAct2")}</li>
          <li>{t("rmCapacityGuideAct3")}</li>
        </ul>

        <p className="fc-split-heading">{t("rmStyleGuideTitle")}</p>
        <ul>
          <li>{t("rmStyleGuide1")}</li>
          <li>{t("rmStyleGuide2")}</li>
          <li>{t("rmStyleGuide3")}</li>
          <li>{t("rmStyleGuide4")}</li>
          <li>{t("rmStyleGuide5")}</li>
        </ul>

        {/* Conversion has no button because it has no REST API: `volume conversion
            start` is an advanced-privilege CLI command, and AWS recommends copying to a
            new FlexGroup rather than converting in place. What this can do is put the
            preconditions and the consequences where somebody is looking at the volume,
            rather than leaving them to find out mid-conversion. */}
        <p className="fc-split-heading">{t("rmConvertTitle")}</p>
        <ul>
          <li>{t("rmConvert1")}</li>
          <li>{t("rmConvert2")}</li>
          <li>{t("rmConvert3")}</li>
          <li>{t("rmConvert4")}</li>
          <li>{t("rmConvert5")}</li>
          <li>{t("rmConvert6")}</li>
        </ul>
        <p className="rm-hint">
          <code>volume conversion start -vserver &lt;svm&gt; -volume &lt;name&gt;</code>
          {" — "}
          {t("rmConvertCommandNote")}
        </p>

        <p className="fc-split-heading">{t("rmBackupTitle")}</p>
        <ul>
          <li>{t("rmBackup1")}</li>
          <li>{t("rmBackup2")}</li>
          <li>{t("rmBackup3")}</li>
          <li>{t("rmBackup4")}</li>
        </ul>

        <p className="rm-hint">
          {t("fcSplitSources")}:{" "}
          <a
            href="https://docs.netapp.com/us-en/ontap/data-protection/manage-snapshot-copy-reserve-concept.html"
            target="_blank"
            rel="noreferrer"
          >
            ONTAP docs
          </a>
          {" / "}
          <a
            href="https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/ONTAP_OS/What_can_impact_snapshot_size_and_cause_snapshot_spill"
            target="_blank"
            rel="noreferrer"
          >
            NetApp KB
          </a>
          {" / "}
          <a
            href="https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/managing-volumes.html"
            target="_blank"
            rel="noreferrer"
          >
            AWS docs
          </a>
        </p>
      </details>

      {rebalancing && (
        <VolumeRebalancePanel
          volumeUuid={rebalancing.uuid}
          volumeName={rebalancing.name}
          onClose={() => setRebalancing(null)}
        />
      )}

      {mounting && (
        <VolumeMountPanel
          volumeUuid={mounting.uuid}
          volumeName={mounting.name}
          onClose={() => setMounting(null)}
          // Each row shows its junction path, so a mount made in the panel has to
          // reach this list or the row goes on showing the state before it.
          onChanged={loadVolumes}
        />
      )}

      <table className="admin-table">
        <thead>
          <tr>
            <th>{t("rmVolumeName")}</th>
            <th>{t("rmVolumeStyle")}</th>
            <th>{t("rmVolumeSize")}</th>
            <th>{t("rmUsed")}</th>
            <th>{t("rmState")}</th>
            <th>{t("rmSecurityStyle")}</th>
            <th>{t("rmActions")}</th>
          </tr>
        </thead>
        <tbody>
          {volumes.map((vol) => (
            <tr key={vol.uuid}>
              <td className="vol-name">
                {vol.name}
                {vol.snaplockType !== "non_snaplock" && <span className="badge-lock">🔒</span>}
                {/* The path clients reach the volume through, under the name it
                    belongs to rather than in a column of its own -- the table is
                    already wide, and the two are read together.

                    An unmounted volume is called out rather than shown as blank. It is
                    listed as online and reaches no client, which looks like a healthy
                    row until somebody tries to use it. */}
                {vol.junctionPath ? (
                  <small className="vol-junction">{vol.junctionPath}</small>
                ) : (
                  <small className="vol-junction vol-junction-none" title={t("rmUnmountedTitle")}>
                    {t("rmUnmounted")}
                  </small>
                )}
              </td>
              <td>
                <span className={`vol-style-badge style-${vol.style}`} title={t(styleTitleKey(vol.style))}>
                  {styleLabel(vol.style)}
                </span>
                {/* A FlexCache's cache side is a FlexGroup whether or not anybody chose
                    that, and it does not support snapshots, quotas, qtrees or cloning.
                    Saying only "FlexGroup" here would invite those operations. */}
                {vol.flexcacheEndpointType === "cache" && (
                  <small className="vol-style-note">{t("rmFlexcacheCacheNote")}</small>
                )}
                {vol.flexcacheEndpointType === "origin" && (
                  <small className="vol-style-note">{t("rmFlexcacheOriginNote")}</small>
                )}
              </td>
              <td>{vol.sizeGiB} GiB</td>
              <td>
                {/* Two segments: live data, then snapshot data that has outgrown the
                    reserve. They add up to the percentage beside them, because ONTAP's
                    `used` counts the spill and not the snapshot data still inside the
                    reserve. */}
                <div className="capacity-bar" title={t("rmCapacityBarTitle")}>
                  <div className="capacity-fill" style={{ width: `${Math.min(afsPercent(vol), 100)}%`,
                    backgroundColor: vol.usedPercent > 90 ? "var(--color-error)" : vol.usedPercent > 75 ? "var(--color-warning)" : "var(--color-success)" }} />
                  {vol.snapshotSpillBytes > 0 && (
                    <div className="capacity-fill capacity-fill-snapshot"
                      style={{ width: `${Math.min(spillPercent(vol), 100)}%` }} />
                  )}
                </div>
                <span className="capacity-label">{vol.usedPercent}%</span>
                <div className="capacity-breakdown">
                  <span>{t("rmAfsUsed")}: {capacityLabel(vol.afsUsedBytes)}</span>
                  <span>
                    {t("rmSnapshotUsed")}: {capacityLabel(vol.snapshotUsedBytes)}
                    {vol.snapshotReservePercent > 0 &&
                      ` / ${t("rmSnapshotReserve")} ${vol.snapshotReservePercent}%`}
                  </span>
                  {vol.snapshotSpillBytes > 0 && (
                    <span className="capacity-spill" title={t("rmSnapshotSpillTitle")}>
                      ⚠ {t("rmSnapshotSpill")}: {capacityLabel(vol.snapshotSpillBytes)}
                    </span>
                  )}
                </div>
              </td>
              <td><span className={`state-badge state-${vol.state}`}>{vol.state}</span></td>
              <td>{vol.securityStyle}</td>
              <td className="action-cell">
                <button onClick={() => handleResize(vol.uuid, vol.name)} className="btn-sm"
                  title={t("rmResize")}>↔</button>
                {/* Offered on every row, mounted or not: the panel is both where a
                    junction is set and where the mount command for an already-mounted
                    volume is read. */}
                <button onClick={() => setMounting({ uuid: vol.uuid, name: vol.name })}
                  className="btn-sm" title={t("vmOpenTitle")}>⇱</button>
                {/* FlexGroup only, because the operation exists only there. Offering it
                    on a FlexVol and refusing on click would make the style column
                    decorative. */}
                {vol.style === "flexgroup" && (
                  <button onClick={() => setRebalancing({ uuid: vol.uuid, name: vol.name })}
                    className="btn-sm" title={t("rblOpenTitle")}>⇄</button>
                )}
                {/* Offered only where it applies. A delete takes the volume offline before
                    removing it, and a delete that then fails -- ONTAP refuses one whose
                    clone was deleted moments earlier -- leaves it offline, with its
                    clients cut off and nothing here able to undo the step that worked. */}
                {vol.state === "offline" && (
                  <button onClick={() => handleBringOnline(vol.uuid, vol.name)} className="btn-sm"
                    title={t("rmBringOnlineTitle")}>{t("rmBringOnline")}</button>
                )}
                <button onClick={() => handleDelete(vol.uuid, vol.name)} className="btn-sm btn-danger"
                  title={t("rmDelete")}>✕</button>
              </td>
            </tr>
          ))}
          {volumes.length === 0 && (
            <tr><td colSpan={7} className="empty-state">{t("rmNoVolumes")}</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
