import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage, unwrap } from "../../lib/portalQuery";
import { adminMutate, dispatch } from "../../lib/dispatch";
import type { VolumeUuid } from "../../lib/dispatchActions";
import { durationLabel, elapsedLabel } from "../../utils/duration";

/**
 * ONTAP's own state values. The panel maps them to sentences rather than showing the
 * identifier, because "not_running" and "paused" mean different things to somebody
 * deciding whether to press start.
 */
type RebalanceState =
  | "not_running"
  | "starting"
  | "rebalancing"
  | "paused"
  | "stopping"
  | "unknown"
  // Two states ONTAP returns for a volume and does not list among the volume-level
  // values. Both measured here: `idle` is a running operation with nothing to move --
  // it stayed there for the whole runtime on a volume with no file over the 100 MB
  // minimum -- and `scheduled` is a start registered for a future time. Without them
  // a running rebalance rendered as "unknown".
  | "idle"
  | "scheduled";

interface Rebalance {
  state: RebalanceState;
  imbalancePercent: number;
  imbalanceBytes: number;
  maxConstituentImbalancePercent: number;
  targetUsedBytes: number;
  usedForImbalanceBytes: number;
  dataMovedBytes: number;
  runtime: string;
  startTime: string;
  stopTime: string;
  maxRuntime: string;
  minFileSizeBytes: number;
  maxThresholdPercent: number;
  minThresholdPercent: number;
  maxFileMoves: number;
  excludeSnapshots: boolean;
  /** What the scanner has looked at, and what it declined to move and why. */
  filesScanned: number;
  fileMovesStarted: number;
  filesSkipped: Record<string, number>;
  notices: string[];
}

interface Constituent {
  name: string;
  sizeBytes: number;
  usedBytes: number;
}

interface RebalanceStatus {
  supported: boolean;
  /** "NOT_FLEXGROUP" | "OBJECT_STORE" when unsupported. */
  reason?: string;
  volumeStyle?: string;
  constituentCount?: number;
  /** Whether ONTAP returned a rebalancing object. Not the same as state "unknown". */
  reported?: boolean;
  granularData?: boolean;
  granularDataMode?: string;
  constituents?: Constituent[];
  rebalance: Rebalance | null;
}

const BYTES_PER_MIB = 1024 ** 2;

function sizeLabel(bytes: number): string {
  if (bytes <= 0) return "0 B";
  if (bytes < BYTES_PER_MIB) return `${(bytes / 1024).toFixed(0)} KiB`;
  if (bytes < 1024 ** 3) return `${(bytes / BYTES_PER_MIB).toFixed(1)} MiB`;
  if (bytes < 1024 ** 4) return `${(bytes / 1024 ** 3).toFixed(1)} GiB`;
  return `${(bytes / 1024 ** 4).toFixed(2)} TiB`;
}

/** Literal keys, so a state ONTAP adds later shows as unknown rather than as a raw key. */
function stateKey(state: RebalanceState) {
  switch (state) {
    case "not_running":
      return "rblStateNotRunning" as const;
    case "starting":
      return "rblStateStarting" as const;
    case "rebalancing":
      return "rblStateRebalancing" as const;
    case "idle":
      return "rblStateIdle" as const;
    case "scheduled":
      return "rblStateScheduled" as const;
    case "paused":
      return "rblStatePaused" as const;
    case "stopping":
      return "rblStateStopping" as const;
    default:
      return "rblStateUnknown" as const;
  }
}

/** Whether an operation exists on the volume, scheduled or running. */
function inProgress(state: RebalanceState | undefined): boolean {
  return state !== undefined && state !== "not_running" && state !== "unknown";
}

/**
 * The runtimes offered, shortest first.
 *
 * 30 minutes leads because it is the only one that is always allowed to be tried:
 * ONTAP refuses anything shorter outright, and refuses anything that reaches past
 * the volume's next scheduled snapshot. With the default snapshot policy, which
 * takes an hourly snapshot at :05, that leaves 30 minutes as the only option that
 * can start at all -- and only between :05 and :35. Offering 6 hours first, as this
 * did, meant the button failed every time on a volume with a snapshot policy.
 */
const MAX_RUNTIMES = ["PT30M", "PT1H", "PT2H", "PT6H", "PT12H", "P1D", "P3D"];

interface Props {
  volumeUuid: VolumeUuid;
  volumeName: string;
  onClose: () => void;
}

/**
 * Capacity rebalancing for one FlexGroup volume.
 *
 * A FlexGroup places a file on a constituent by hash, not by how full that
 * constituent is, so the members drift apart as files are added and grow. The volume
 * then reports no space when any single constituent is full, however much room the
 * others have -- which is why the imbalance figures here matter more than the volume's
 * overall used percentage.
 *
 * Kept out of the volume table because the decision needs a dozen numbers and two
 * warnings, and the table has room for neither.
 */
export function VolumeRebalancePanel({ volumeUuid, volumeName, onClose }: Props) {
  const { t } = useTranslation();
  const [actionError, setActionError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  // The first of MAX_RUNTIMES, not ONTAP's own default of 6 hours. Reordering that
  // list left this behind, so the select still opened on the one value that cannot
  // start on a volume with a snapshot policy.
  const [maxRuntime, setMaxRuntime] = useState(MAX_RUNTIMES[0]);

  const {
    data: status,
    isPending,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "getVolumeRebalance", volumeUuid],
    queryFn: () =>
      unwrap<RebalanceStatus>(dispatch("adminQuery", { action: "getVolumeRebalance", params: { volumeUuid } })),
    // While files are moving the interesting numbers change: ONTAP refreshes the worst
    // constituent's imbalance every 10 seconds during a rebalance and every 30 when
    // idle. A static panel would show the operation as though it were stuck.
    refetchInterval: (query) =>
      inProgress(query.state.data?.rebalance?.state) ? 10_000 : false,
  });

  const error = actionError ?? errorMessage(queryError, "Failed to read rebalance status");

  const handleStart = async () => {
    // The consequence is small in cost and permanent in effect, so it is stated in
    // full rather than summarised: granular data cannot be switched off again.
    if (!window.confirm(t("rblStartConfirm").replace("{name}", volumeName))) return;
    setActionError(null);
    setResult(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "startVolumeRebalance",
        // No volumeName: the start path reads the volume's own record and logs the
        // name from there, so sending one would be a parameter nothing reads.
        params: { volumeUuid, maxRuntime, acknowledgeIrreversible: true },
      });
      if (data?.success) {
        setResult(t("rblStarted"));
        void refetch();
      } else setActionError(data?.error || t("rmActionFailed"));
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t("rmActionFailed"));
    }
  };

  const handleStop = async () => {
    setActionError(null);
    setResult(null);
    try {
      const data = await adminMutate<{ success?: boolean }>({
        action: "stopVolumeRebalance",
        params: { volumeUuid, volumeName },
      });
      if (data?.success) {
        setResult(t("rblStopped"));
        void refetch();
      } else setActionError(data?.error || t("rmActionFailed"));
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t("rmActionFailed"));
    }
  };

  const rebalance = status?.rebalance ?? null;
  const running = inProgress(rebalance?.state);
  const scheduled = rebalance?.state === "scheduled";

  return (
    <div className="rebalance-panel">
      <div className="panel-header">
        <h4>
          {t("rblTitle")} — {volumeName}
        </h4>
        <div className="panel-actions">
          <button onClick={() => void refetch()} className="refresh-btn" title={t("refresh")}>
            ↻
          </button>
          <button onClick={onClose} className="btn-secondary">
            {t("close")}
          </button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}
      {result && <div className="success-message">{result}</div>}

      {isPending && <p className="loading">{t("loading")}</p>}

      {/* Not offered, and why. The style is the usual reason; an ONTAP S3 bucket's
          backing volume is the other, and it is a FlexGroup, so the style alone would
          suggest the operation should be available. */}
      {status && !status.supported && (
        <div className="info-message">
          {status.reason === "OBJECT_STORE"
            ? t("rblObjectStore")
            : t("rblNotFlexgroup").replace("{style}", status.volumeStyle || "—")}
        </div>
      )}

      {/* Supported by style, but ONTAP is not reporting the object. Measured on this
          file system: a FlexCache cache volume is a FlexGroup and carries no
          rebalancing object even when every field is requested. Offering start here
          would be offering an operation ONTAP has not said it tracks. */}
      {status?.supported && !status.reported && (
        <div className="info-message">{t("rblNotReported")}</div>
      )}

      {status?.supported && status.reported && rebalance && (
        <>
          <div className="rebalance-status">
            <div>
              <span className="rebalance-label">{t("rblState")}</span>
              <span className={`state-badge state-${rebalance.state}`}>{t(stateKey(rebalance.state))}</span>
            </div>
            <div>
              <span className="rebalance-label">{t("rblConstituents")}</span>
              <span>{status.constituentCount}</span>
            </div>
            <div>
              <span className="rebalance-label">{t("rblImbalance")}</span>
              <span>
                {rebalance.imbalancePercent}% ({sizeLabel(rebalance.imbalanceBytes)})
              </span>
            </div>
            {/* The number that decides whether rebalancing is worth running. A volume
                can read 0% overall while one constituent is far past the threshold,
                and it is the constituent that returns "no space". */}
            <div>
              <span className="rebalance-label">{t("rblWorstConstituent")}</span>
              <span>{rebalance.maxConstituentImbalancePercent}%</span>
            </div>
            {/* ONTAP computes this while a rebalance is running and reports zero
                otherwise, so a bare "0" would read as a target of nothing. */}
            <div>
              <span className="rebalance-label">{t("rblTargetUsed")}</span>
              <span>{rebalance.targetUsedBytes > 0 ? sizeLabel(rebalance.targetUsedBytes) : "—"}</span>
            </div>
            {/* Only while something exists to describe. `startTime` outlives the
                operation it belonged to: after a scheduled start is cancelled, ONTAP
                keeps the cancelled timestamp there with a `stopTime` beside it, so
                showing it unconditionally announces a run that is not going to
                happen. */}
            {scheduled && (
              <div>
                <span className="rebalance-label">{t("rblScheduledFor")}</span>
                <span>{rebalance.startTime || "—"}</span>
              </div>
            )}
            {running && !scheduled && (
              <>
                <div>
                  <span className="rebalance-label">{t("rblDataMoved")}</span>
                  <span>{sizeLabel(Math.abs(rebalance.dataMovedBytes))}</span>
                </div>
                <div>
                  <span className="rebalance-label">{t("rblRuntime")}</span>
                  <span>{rebalance.runtime ? elapsedLabel(rebalance.runtime) : "—"}</span>
                </div>
                {/* Why nothing is moving. A rebalance with no file over the minimum
                    reports `idle` with every counter at zero and emits no notice, so
                    without these the panel cannot tell "working" from "found nothing
                    to work on". */}
                <div>
                  <span className="rebalance-label">{t("rblFilesScanned")}</span>
                  <span>
                    {rebalance.filesScanned} / {t("rblFileMovesStarted")} {rebalance.fileMovesStarted}
                  </span>
                </div>
                {Object.keys(rebalance.filesSkipped).length > 0 && (
                  <div>
                    <span className="rebalance-label">{t("rblFilesSkipped")}</span>
                    <span>
                      {Object.entries(rebalance.filesSkipped)
                        .map(([reason, count]) => `${reason}: ${count}`)
                        .join(", ")}
                    </span>
                  </div>
                )}
              </>
            )}
          </div>

          {/* The members themselves. The percentages above summarise these, and a
              summary cannot be acted on: the volume reports no space when one member
              fills, so the member list is where that is visible. */}
          {status.constituents && status.constituents.length > 0 && (
            <details className="rm-guide">
              <summary>
                {t("rblConstituentsTitle")} ({status.constituents.length})
              </summary>
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>{t("rmVolumeName")}</th>
                    <th>{t("rmVolumeSize")}</th>
                    <th>{t("rmUsed")}</th>
                  </tr>
                </thead>
                <tbody>
                  {status.constituents.map((constituent) => (
                    <tr key={constituent.name}>
                      <td>{constituent.name}</td>
                      <td>{sizeLabel(constituent.sizeBytes)}</td>
                      <td>
                        {sizeLabel(constituent.usedBytes)} (
                        {((constituent.usedBytes / Math.max(constituent.sizeBytes, 1)) * 100).toFixed(1)}%)
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="rm-hint">{t("rblConstituentsNote")}</p>
            </details>
          )}

          {rebalance.notices.length > 0 && (
            <div className="info-message">
              <strong>{t("rblNotices")}</strong>
              <ul>
                {rebalance.notices.map((notice) => (
                  <li key={notice}>{notice}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="rebalance-actions">
            {running ? (
              // Stop is also how a scheduled start is cancelled, so it says which of
              // the two it is about to do.
              <button onClick={() => void handleStop()} className="btn-secondary">
                {scheduled ? t("rblCancelSchedule") : t("rblStop")}
              </button>
            ) : (
              <>
                <label htmlFor="rebalance-max-runtime">{t("rblMaxRuntime")}</label>
                <select
                  id="rebalance-max-runtime"
                  value={maxRuntime}
                  onChange={(e) => setMaxRuntime(e.target.value)}
                >
                  {MAX_RUNTIMES.map((period) => (
                    <option key={period} value={period}>
                      {durationLabel(period, t)}
                    </option>
                  ))}
                </select>
                <button onClick={() => void handleStart()} className="btn-primary">
                  {t("rblStart")}
                </button>
              </>
            )}
          </div>

          {/* The settings the next operation will use, read from the volume rather than
              assumed. ONTAP holds them on the volume and a running operation ignores
              changes to them, so they are labelled as applying to the next run. */}
          <details className="rm-guide">
            <summary>{t("rblSettingsTitle")}</summary>
            <ul>
              <li>
                {t("rblMinFileSize")}: {sizeLabel(rebalance.minFileSizeBytes)}
              </li>
              <li>
                {t("rblThresholds")}: {rebalance.maxThresholdPercent}% / {rebalance.minThresholdPercent}%
              </li>
              <li>
                {t("rblMaxFileMoves")}: {rebalance.maxFileMoves}
              </li>
              <li>
                {t("rblExcludeSnapshots")}: {rebalance.excludeSnapshots ? t("rblYes") : t("rblNo")}
              </li>
              <li>
                {t("rblGranularData")}: {status.granularDataMode || "—"}
              </li>
            </ul>
            <p className="rm-hint">{t("rblSettingsNote")}</p>
          </details>
        </>
      )}

      {/* Shown whatever the state, including where the operation is not offered: the
          reasons it is not offered are part of what somebody reading this needs. */}
      <details className="rm-guide">
        <summary>{t("rblGuideTitle")}</summary>
        <ul>
          <li>{t("rblGuide1")}</li>
          <li>{t("rblGuide2")}</li>
          <li>{t("rblGuide3")}</li>
          <li>{t("rblGuide4")}</li>
          <li>{t("rblGuide5")}</li>
          <li>{t("rblGuide6")}</li>
          <li>{t("rblGuide7")}</li>
          {/* The two bounds on the runtime, and the window they leave. Neither is in
              the REST reference; both were measured, and together they are the reason
              a start is refused far more often than anything else. */}
          <li>{t("rblGuide8")}</li>
          <li>{t("rblGuide9")}</li>
        </ul>
        <p className="rm-hint">
          {t("fcSplitSources")}:{" "}
          <a
            href="https://docs.netapp.com/us-en/ontap/flexgroup/manage-flexgroup-rebalance-task.html"
            target="_blank"
            rel="noreferrer"
          >
            ONTAP docs
          </a>
          {" / "}
          <a
            href="https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/expanding-fg-volumes.html"
            target="_blank"
            rel="noreferrer"
          >
            AWS docs
          </a>
        </p>
        {/* The measurements behind every number in this panel. Linked from here because
            the two runtime bounds are not in either vendor's reference, so a reader who
            doubts them has nowhere else to go. */}
        <p className="rm-hint">
          <a
            href="https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/blob/main/solutions/amplify-portal/docs/flexgroup-rebalance-verification.md"
            target="_blank"
            rel="noreferrer"
          >
            📋 {t("rblVerificationLink")}
          </a>
        </p>
      </details>
    </div>
  );
}
