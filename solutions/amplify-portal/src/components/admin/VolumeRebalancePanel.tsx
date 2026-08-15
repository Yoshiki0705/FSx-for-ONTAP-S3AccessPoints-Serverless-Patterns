import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { errorMessage, unwrap } from "../../lib/portalQuery";
import { adminMutate, dispatch } from "../../lib/dispatch";
import type { VolumeUuid } from "../../lib/dispatchActions";
import { durationLabel } from "../../utils/duration";

/**
 * ONTAP's own state values. The panel maps them to sentences rather than showing the
 * identifier, because "not_running" and "paused" mean different things to somebody
 * deciding whether to press start.
 */
type RebalanceState = "not_running" | "starting" | "rebalancing" | "paused" | "stopping" | "unknown";

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
  notices: string[];
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
  rebalance: Rebalance | null;
}

const BYTES_PER_MIB = 1024 ** 2;

function sizeLabel(bytes: number): string {
  if (bytes <= 0) return "0";
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
    case "paused":
      return "rblStatePaused" as const;
    case "stopping":
      return "rblStateStopping" as const;
    default:
      return "rblStateUnknown" as const;
  }
}

/** The runtimes offered. ONTAP's own default is 6 hours and stands first. */
const MAX_RUNTIMES = ["PT6H", "PT1H", "PT2H", "PT12H", "P1D", "P3D"];

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
  const [maxRuntime, setMaxRuntime] = useState("PT6H");

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
    refetchInterval: (query) => {
      const state = query.state.data?.rebalance?.state;
      return state === "rebalancing" || state === "starting" || state === "stopping" ? 10_000 : false;
    },
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
  const running = rebalance?.state === "rebalancing" || rebalance?.state === "starting";

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
            {running && (
              <>
                <div>
                  <span className="rebalance-label">{t("rblDataMoved")}</span>
                  <span>{sizeLabel(Math.abs(rebalance.dataMovedBytes))}</span>
                </div>
                <div>
                  <span className="rebalance-label">{t("rblRuntime")}</span>
                  <span>{rebalance.runtime || "—"}</span>
                </div>
              </>
            )}
          </div>

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
            {running || rebalance.state === "paused" ? (
              <button onClick={() => void handleStop()} className="btn-secondary">
                {t("rblStop")}
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
      </details>
    </div>
  );
}
