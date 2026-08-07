import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "../../i18n";
import { dispatch } from "../../lib/dispatch";
import { errorMessage, unwrap } from "../../lib/portalQuery";

interface VolumeEfficiency {
  name: string;
  dedupEnabled: boolean;
  compressionEnabled: boolean;
  logicalUsedGiB: number;
  physicalUsedGiB: number;
  savingsRatio: string;
}

interface EfficiencyStats {
  overallRatio: string;
  overallSavingsPercent: number;
  volumes: VolumeEfficiency[];
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
      unwrap<{ stats?: EfficiencyStats }>(
        dispatch("adminQuery", { action: "getEfficiencyStats" }),
      ),
  });

  const stats = data?.stats ?? null;
  const error = errorMessage(queryError, "Failed to load efficiency stats");

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

      {!stats ? (
        <p className="empty-state">{t("rmNoEfficiencyData")}</p>
      ) : (
        <>
          <div className="form-row" style={{ marginBottom: "1.5rem" }}>
            <div className="form-group" style={{ textAlign: "center", padding: "1rem", border: "1px solid var(--border-color)", borderRadius: "8px" }}>
              <div style={{ fontSize: "2rem", fontWeight: 700 }}>{stats.overallRatio}</div>
              <div>{t("rmOverallRatio")}</div>
            </div>
            <div className="form-group" style={{ textAlign: "center", padding: "1rem", border: "1px solid var(--border-color)", borderRadius: "8px" }}>
              <div style={{ fontSize: "2rem", fontWeight: 700 }}>{stats.overallSavingsPercent}%</div>
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
              {stats.volumes.map((v) => (
                <tr key={v.name}>
                  <td>{v.name}</td>
                  <td>
                    <span className={`state-badge state-${v.dedupEnabled ? "online" : "offline"}`}>
                      {v.dedupEnabled ? "Enabled" : "None"}
                    </span>
                  </td>
                  <td>
                    <span className={`state-badge state-${v.compressionEnabled ? "online" : "offline"}`}>
                      {v.compressionEnabled ? "Enabled" : "None"}
                    </span>
                  </td>
                  <td>{v.logicalUsedGiB} GiB</td>
                  <td>{v.physicalUsedGiB} GiB</td>
                  <td>{v.savingsRatio}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
