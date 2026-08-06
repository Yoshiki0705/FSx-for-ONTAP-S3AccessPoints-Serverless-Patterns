import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../../amplify/data/resource";
import { useTranslation } from "../../i18n";
import { parseResponse } from "../../utils/parseResponse";

const client = generateClient<Schema>();

interface DashboardData {
  volumeCount: number;
  volumeCapacityPct: number;
  arpThreats: number;
  arpProtected: number;
  lockedSnapshots: number;
  efficiencyRatio: number;
}

/**
 * Storage Health Dashboard — admin landing page overview.
 *
 * Pattern from ONTAP System Manager: "dashboard first" showing health at a glance.
 * 4 cards: Capacity, ARP/AI Protection, Locked Snapshots, Storage Efficiency.
 */
export function StorageDashboard({ onNavigate }: { onNavigate: (panel: string) => void }) {
  const { t } = useTranslation();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        // Parallel fetch for all dashboard data
        const [volResp, arpResp, snapResp, effResp] = await Promise.allSettled([
          client.queries.adminQuery({ action: "listVolumes", params: JSON.stringify({}) }),
          client.queries.adminQuery({ action: "listArpVolumes", params: JSON.stringify({}) }),
          client.queries.protectionQuery({ action: "listSnapshots", params: JSON.stringify({ maxResults: 50 }) }),
          client.queries.adminQuery({ action: "getEfficiencyStats", params: JSON.stringify({}) }),
        ]);

        let volumeCount = 0, volumeCapacityPct = 0;
        if (volResp.status === "fulfilled") {
          // `name` is read below but was missing from this type; the `any` on the
          // filter callback hid that, so the property was never checked.
          const vd = parseResponse<{ volumes?: { name?: string; usedPercent?: number }[] }>(volResp.value);
          if (vd?.volumes) {
            const userVols = vd.volumes.filter((v) => !v.name?.endsWith("_root"));
            volumeCount = userVols.length;
            volumeCapacityPct = userVols.length > 0
              ? Math.round(userVols.reduce((sum, v) => sum + (v.usedPercent || 0), 0) / userVols.length)
              : 0;
          }
        }

        let arpThreats = 0, arpProtected = 0;
        if (arpResp.status === "fulfilled") {
          const ad = parseResponse<{ volumes?: { state: string; threat?: string }[] }>(arpResp.value);
          if (ad?.volumes) {
            arpProtected = ad.volumes.filter((v) => v.state === "enabled" || v.state === "dry_run").length;
            arpThreats = ad.volumes.filter((v) => v.threat && v.threat !== "none").length;
          }
        }

        let lockedSnapshots = 0;
        if (snapResp.status === "fulfilled") {
          const sd = parseResponse<{ snapshots?: { isLocked: boolean }[] }>(snapResp.value);
          if (sd?.snapshots) {
            lockedSnapshots = sd.snapshots.filter((s) => s.isLocked).length;
          }
        }

        let efficiencyRatio = 1.0;
        if (effResp.status === "fulfilled") {
          const ed = parseResponse<{ overallRatio?: number }>(effResp.value);
          if (ed?.overallRatio) efficiencyRatio = ed.overallRatio;
        }

        setData({ volumeCount, volumeCapacityPct, arpThreats, arpProtected, lockedSnapshots, efficiencyRatio });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Dashboard load failed");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) return <p className="loading">{t("loading")}</p>;
  if (error) return <div className="error-message">{error}</div>;
  if (!data) return null;

  return (
    <div className="storage-dashboard">
      <h3>{t("dashTitle")}</h3>
      <div className="dashboard-grid">
        {/* Card 1: Volume Capacity */}
        <div className="dashboard-card" onClick={() => onNavigate("volumes")} style={{ cursor: "pointer" }}>
          <div className="card-icon">💾</div>
          <div className="card-content">
            <div className="card-value">{data.volumeCount}</div>
            <div className="card-label">{t("dashVolumes")}</div>
            <div className={`card-metric ${data.volumeCapacityPct > 85 ? "metric-warning" : "metric-ok"}`}>
              {t("dashAvgCapacity")}: {data.volumeCapacityPct}%
            </div>
          </div>
        </div>

        {/* Card 2: ARP/AI Protection */}
        <div className="dashboard-card" onClick={() => onNavigate("arp")} style={{ cursor: "pointer" }}>
          <div className="card-icon">{data.arpThreats > 0 ? "🚨" : "🛡️"}</div>
          <div className="card-content">
            <div className="card-value">{data.arpProtected}</div>
            <div className="card-label">{t("dashArpProtected")}</div>
            <div className={`card-metric ${data.arpThreats > 0 ? "metric-danger" : "metric-ok"}`}>
              {data.arpThreats > 0 ? `⚠️ ${data.arpThreats} ${t("dashThreats")}` : `✅ ${t("dashNoThreats")}`}
            </div>
          </div>
        </div>

        {/* Card 3: Locked Snapshots */}
        <div className="dashboard-card" onClick={() => onNavigate("snapshotAdmin")} style={{ cursor: "pointer" }}>
          <div className="card-icon">🔐</div>
          <div className="card-content">
            <div className="card-value">{data.lockedSnapshots}</div>
            <div className="card-label">{t("dashLockedSnaps")}</div>
            <div className="card-metric metric-ok">{t("dashTamperproof")}</div>
          </div>
        </div>

        {/* Card 4: Storage Efficiency */}
        <div className="dashboard-card" onClick={() => onNavigate("efficiency")} style={{ cursor: "pointer" }}>
          <div className="card-icon">📊</div>
          <div className="card-content">
            <div className="card-value">{data.efficiencyRatio}x</div>
            <div className="card-label">{t("dashEfficiency")}</div>
            <div className="card-metric metric-ok">
              {Math.round((1 - 1 / data.efficiencyRatio) * 100)}% {t("dashSaved")}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
