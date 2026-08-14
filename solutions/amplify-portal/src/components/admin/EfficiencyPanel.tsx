import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { dispatch } from "../../lib/dispatch";
import { errorMessage, unwrap } from "../../lib/portalQuery";

/** One volume as `getEfficiencyStats` returns it.
 *
 * The names and units are the handler's, not this component's: `dedupe` and
 * `compression` are ONTAP's own enum strings ("none", "background", "inline",
 * "inline_and_background") rather than booleans, and the sizes are bytes. An
 * earlier version of this file declared a `dedupEnabled`/`logicalUsedGiB` shape
 * nested under `stats`, which the handler never sent, so the panel read
 * `undefined` and rendered the empty state on every load.
 */
interface VolumeEfficiency {
  name: string;
  dedupe: string;
  compression: string;
  logicalUsedBytes: number;
  physicalUsedBytes: number;
  savingsRatio: number;
}

interface EfficiencySummary {
  overallRatio: number;
  overallSavingsPercent: number;
}

interface EfficiencyResponse {
  volumes?: VolumeEfficiency[];
  summary?: EfficiencySummary;
  error?: string | null;
}

const BYTES_PER_GIB = 1024 ** 3;

/** ONTAP reports the policy, not a flag. Anything but "none" means it is on. */
function isOn(setting: string | undefined): boolean {
  return !!setting && setting !== "none";
}

function toGiB(bytes: number | undefined): string {
  return ((bytes ?? 0) / BYTES_PER_GIB).toFixed(1);
}

export function EfficiencyPanel() {
  const { t } = useTranslation();

  const {
    data,
    isPending,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["admin", "getEfficiencyStats"],
    queryFn: () =>
      unwrap<EfficiencyResponse>(
        dispatch("adminQuery", { action: "getEfficiencyStats" }),
      ),
  });

  const volumes = data?.volumes ?? [];
  const summary = data?.summary ?? null;
  // The handler reports an ONTAP-side failure in the payload rather than by
  // rejecting, so surface that too instead of showing "no data" for an error.
  const error = data?.error || errorMessage(queryError, "Failed to load efficiency stats");

  if (isPending) return <p className="loading">{t("loading")}</p>;

  return (
    <div className="admin-panel">
      <div className="panel-header">
        <h3>{t("rmEfficiency")}</h3>
        <div className="panel-actions">
          <button onClick={() => void refetch()} className="refresh-btn">↻</button>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      {volumes.length === 0 ? (
        <p className="empty-state">{t("rmNoEfficiencyData")}</p>
      ) : (
        <>
          <div className="form-row" style={{ marginBottom: "1.5rem" }}>
            <div className="form-group" style={{ textAlign: "center", padding: "1rem", border: "1px solid var(--color-border-strong)", borderRadius: "8px" }}>
              <div style={{ fontSize: "2rem", fontWeight: 700 }}>{(summary?.overallRatio ?? 1).toFixed(2)}x</div>
              <div>{t("rmOverallRatio")}</div>
            </div>
            <div className="form-group" style={{ textAlign: "center", padding: "1rem", border: "1px solid var(--color-border-strong)", borderRadius: "8px" }}>
              <div style={{ fontSize: "2rem", fontWeight: 700 }}>{summary?.overallSavingsPercent ?? 0}%</div>
              <div>{t("rmOverallSavings")}</div>
            </div>
          </div>

          <table className="admin-table">
            <thead>
              <tr>
                <th>{t("rmVolumeName")}</th>
                <th>{t("rmDedup")}</th>
                <th>{t("rmCompression")}</th>
                <th>{t("rmLogicalUsed")}</th>
                <th>{t("rmPhysicalUsed")}</th>
                <th>{t("rmSavingsRatio")}</th>
              </tr>
            </thead>
            <tbody>
              {volumes.map((v) => (
                <tr key={v.name}>
                  <td>{v.name}</td>
                  <td>
                    <span className={`state-badge state-${isOn(v.dedupe) ? "online" : "offline"}`}>
                      {isOn(v.dedupe) ? v.dedupe : "none"}
                    </span>
                  </td>
                  <td>
                    <span className={`state-badge state-${isOn(v.compression) ? "online" : "offline"}`}>
                      {isOn(v.compression) ? v.compression : "none"}
                    </span>
                  </td>
                  <td>{toGiB(v.logicalUsedBytes)} GiB</td>
                  <td>{toGiB(v.physicalUsedBytes)} GiB</td>
                  <td>{(v.savingsRatio ?? 1).toFixed(2)}x</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
