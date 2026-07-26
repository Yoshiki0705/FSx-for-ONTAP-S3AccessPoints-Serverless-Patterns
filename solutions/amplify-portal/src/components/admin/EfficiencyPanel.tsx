import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";

const client = generateClient<Schema>();

// Parse the JSON string response from generic dispatch endpoints
function parseResponse<T>(response: { data?: string | null }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === 'string' ? JSON.parse(response.data) : response.data;
  } catch { return null; }
}

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
  const [stats, setStats] = useState<EfficiencyStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadStats = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await (client.queries as any).adminQuery({ action: "getEfficiencyStats", params: JSON.stringify({}) });
      const data = parseResponse<{ stats?: EfficiencyStats; error?: string }>(response);
      if (data) {
        if (data.error) setError(data.error);
        else setStats(data.stats || null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load efficiency stats");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadStats(); }, []);

  if (loading) return <p className="loading">{t("loading")}</p>;

  return (
    <div className="admin-panel">
      <div className="panel-header">
        <h3>{t("rmEfficiency")}</h3>
        <div className="panel-actions">
          <button onClick={loadStats} className="refresh-btn">↻</button>
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
