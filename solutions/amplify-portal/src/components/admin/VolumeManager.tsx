import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage, unwrap } from "../../lib/portalQuery";
import { adminMutate, dispatch } from "../../lib/dispatch";
import { asIsoDuration, type IsoDuration, type VolumeUuid } from "../../lib/dispatchActions";
import { SnaplockConfirmDialog } from "../SnaplockConfirmDialog";
import { durationLabel, durationRange } from "../../utils/duration";
import { oneOf } from "../../utils/oneOf";
import type { SnaplockIntent } from "../../utils/snaplockConsequences";

interface Volume {
  name: string;
  /** ONTAP's UUID, branded where it arrives so the name beside it cannot stand in. */
  uuid: VolumeUuid;
  sizeGiB: number;
  usedPercent: number;
  state: string;
  style: string;
  securityStyle: string;
  snaplockType: string;
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

      <table className="admin-table">
        <thead>
          <tr>
            <th>{t("rmVolumeName")}</th>
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
              </td>
              <td>{vol.sizeGiB} GiB</td>
              <td>
                <div className="capacity-bar">
                  <div className="capacity-fill" style={{ width: `${Math.min(vol.usedPercent, 100)}%`,
                    backgroundColor: vol.usedPercent > 90 ? "#ef4444" : vol.usedPercent > 75 ? "#f97316" : "#22c55e" }} />
                </div>
                <span className="capacity-label">{vol.usedPercent}%</span>
              </td>
              <td><span className={`state-badge state-${vol.state}`}>{vol.state}</span></td>
              <td>{vol.securityStyle}</td>
              <td className="action-cell">
                <button onClick={() => handleResize(vol.uuid, vol.name)} className="btn-sm"
                  title={t("rmResize")}>↔</button>
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
            <tr><td colSpan={6} className="empty-state">{t("rmNoVolumes")}</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
