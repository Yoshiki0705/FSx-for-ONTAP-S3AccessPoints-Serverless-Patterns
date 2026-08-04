import { useState, useEffect } from "react";
import { useTranslation } from "../i18n";
import { VolumeManager } from "./admin/VolumeManager";
import { ExportPolicyManager } from "./admin/ExportPolicyManager";
import { QosPolicyManager } from "./admin/QosPolicyManager";
import { SnaplockManager } from "./admin/SnaplockManager";
import { QuotaManager } from "./admin/QuotaManager";
import { CifsShareManager } from "./admin/CifsShareManager";
import { QtreeManager } from "./admin/QtreeManager";
import { EfficiencyPanel } from "./admin/EfficiencyPanel";
import { ArpAdminManager } from "./admin/ArpAdminManager";
import { SnapshotAdminManager } from "./admin/SnapshotAdminManager";
import { StorageDashboard } from "./admin/StorageDashboard";
import { AiSettingsManager } from "./admin/AiSettingsManager";
import { FlexCacheManager } from "./admin/FlexCacheManager";
import { FlexCloneManager } from "./admin/FlexCloneManager";
import { SnapMirrorStatus } from "./admin/SnapMirrorStatus";
import { LocalUserManager } from "./admin/LocalUserManager";
import { NameMappingManager } from "./admin/NameMappingManager";
import { VscanManager } from "./admin/VscanManager";
import { FPolicyManager } from "./admin/FPolicyManager";
import { PeeringManager } from "./admin/PeeringManager";
import { ClusterManager } from "./admin/ClusterManager";

type AdminPanel =
  | "volumes"
  | "exportPolicies"
  | "qos"
  | "snaplock"
  | "quotas"
  | "cifsShares"
  | "qtrees"
  | "efficiency"
  | "arpAdmin"
  | "snapshotAdmin"
  | "aiSettings"
  | "flexCache"
  | "flexClone"
  | "snapMirror"
  | "localUsers"
  | "nameMapping"
  | "vscan"
  | "fpolicy"
  | "peering"
  | "cluster";

interface PanelDef {
  id: AdminPanel;
  icon: string;
  label: string;
  description: string;
  category: "storage" | "access" | "protection" | "services" | "cluster";
}

interface ResourceManagementProps {
  aiSettings?: { aiAgentEnabled: boolean; aiSearchEnabled: boolean };
  onAiSettingsChange?: (settings: { aiAgentEnabled: boolean; aiSearchEnabled: boolean }) => void;
}

/**
 * Resource Management — Admin section for ONTAP storage operations.
 *
 * UI inspired by ONTAP System Manager's card-based navigation:
 * - Category headers (Storage, Access Control, Protection, AI Services)
 * - Icon cards with description for each management area
 * - Clicking a card opens the detail panel (replaces card grid)
 * - Back button returns to the overview grid
 *
 * All operations require the "storage-admin" Cognito group.
 */
export function ResourceManagement({ aiSettings, onAiSettingsChange }: ResourceManagementProps) {
  const { t } = useTranslation();
  const [activePanel, setActivePanel] = useState<AdminPanel | null>(null);

  // Auto-open sub-panel if redirected from Lock panel
  useEffect(() => {
    const target = sessionStorage.getItem("rm-panel");
    if (target) {
      sessionStorage.removeItem("rm-panel");
      setActivePanel(target as AdminPanel);
    }
  }, []);

  const panels: PanelDef[] = [
    // Storage
    { id: "volumes", icon: "💾", label: t("rmVolumes"), description: t("rmVolumesDesc"), category: "storage" },
    { id: "qtrees", icon: "🌳", label: t("rmQtrees"), description: t("rmQtreesDesc"), category: "storage" },
    { id: "quotas", icon: "📊", label: t("rmQuotas"), description: t("rmQuotasDesc"), category: "storage" },
    { id: "efficiency", icon: "📈", label: t("rmEfficiency"), description: t("rmEfficiencyDesc"), category: "storage" },
    { id: "flexCache", icon: "⚡", label: t("rmFlexCache"), description: t("rmFlexCacheDesc"), category: "storage" },
    { id: "flexClone", icon: "🧬", label: t("rmFlexClone"), description: t("rmFlexCloneDesc"), category: "storage" },
    // Access Control
    { id: "exportPolicies", icon: "📋", label: t("rmExportPolicies"), description: t("rmExportPoliciesDesc"), category: "access" },
    { id: "cifsShares", icon: "📁", label: t("rmCifsShares"), description: t("rmCifsSharesDesc"), category: "access" },
    { id: "qos", icon: "⚡", label: t("rmQosPolicies"), description: t("rmQosPoliciesDesc"), category: "access" },
    { id: "localUsers", icon: "👤", label: t("rmLocalUsers"), description: t("rmLocalUsersDesc"), category: "access" },
    { id: "nameMapping", icon: "🔗", label: t("rmNameMapping"), description: t("rmNameMappingDesc"), category: "access" },
    // Protection
    { id: "arpAdmin", icon: "🛡️", label: t("rmArpAdmin"), description: t("rmArpAdminDesc"), category: "protection" },
    { id: "snapshotAdmin", icon: "📸", label: t("rmSnapshotAdmin"), description: t("rmSnapshotAdminDesc"), category: "protection" },
    { id: "snaplock", icon: "🔒", label: t("rmSnaplock"), description: t("rmSnaplockDesc"), category: "protection" },
    { id: "snapMirror", icon: "🔄", label: t("rmSnapMirror"), description: t("rmSnapMirrorDesc"), category: "protection" },
    { id: "vscan", icon: "🦠", label: t("rmVscan"), description: t("rmVscanDesc"), category: "protection" },
    { id: "fpolicy", icon: "📜", label: t("rmFpolicy"), description: t("rmFpolicyDesc"), category: "protection" },
    // Cluster — the areas the AWS console does not cover
    { id: "peering", icon: "🔗", label: t("rmPeering"), description: t("rmPeeringDesc"), category: "cluster" },
    { id: "cluster", icon: "🖥️", label: t("rmCluster"), description: t("rmClusterDesc"), category: "cluster" },
    // AI & Services
    { id: "aiSettings", icon: "🤖", label: t("rmAiSettings"), description: t("rmAiSettingsDesc"), category: "services" },
  ];

  const categories = [
    { key: "storage", label: t("rmCatStorage"), icon: "🗄️" },
    { key: "access", label: t("rmCatAccess"), icon: "🔐" },
    { key: "protection", label: t("rmCatProtection"), icon: "🛡️" },
    { key: "cluster", label: t("rmCatCluster"), icon: "🖥️" },
    { key: "services", label: t("rmCatServices"), icon: "🤖" },
  ] as const;

  // Render the detail panel when one is selected
  if (activePanel) {
    const current = panels.find(p => p.id === activePanel);
    return (
      <div className="resource-management">
        <div className="rm-detail-header">
          <button onClick={() => setActivePanel(null)} className="rm-back-btn">
            ← {t("rmBackToOverview")}
          </button>
          <h2>{current?.icon} {current?.label}</h2>
        </div>
        <div className="rm-detail-content">
          {activePanel === "volumes" && <VolumeManager />}
          {activePanel === "quotas" && <QuotaManager />}
          {activePanel === "snapshotAdmin" && <SnapshotAdminManager />}
          {activePanel === "exportPolicies" && <ExportPolicyManager />}
          {activePanel === "cifsShares" && <CifsShareManager />}
          {activePanel === "qtrees" && <QtreeManager />}
          {activePanel === "qos" && <QosPolicyManager />}
          {activePanel === "arpAdmin" && <ArpAdminManager />}
          {activePanel === "snaplock" && <SnaplockManager />}
          {activePanel === "efficiency" && <EfficiencyPanel />}
          {activePanel === "flexCache" && <FlexCacheManager />}
          {activePanel === "flexClone" && <FlexCloneManager />}
          {activePanel === "snapMirror" && <SnapMirrorStatus />}
          {activePanel === "localUsers" && <LocalUserManager />}
          {activePanel === "nameMapping" && <NameMappingManager />}
          {activePanel === "vscan" && <VscanManager />}
          {activePanel === "fpolicy" && <FPolicyManager />}
          {activePanel === "peering" && <PeeringManager />}
          {activePanel === "cluster" && <ClusterManager />}
          {activePanel === "aiSettings" && <AiSettingsManager initialSettings={aiSettings} onSettingsChange={onAiSettingsChange} />}
        </div>
      </div>
    );
  }

  // Render the overview grid
  return (
    <div className="resource-management">
      <div className="rm-overview-header">
        <h2>🔧 {t("rmTitle")}</h2>
        <span className="rm-badge">{t("rmAdminOnly")}</span>
      </div>

      <StorageDashboard onNavigate={(panel) => setActivePanel(panel as AdminPanel)} />

      {categories.map((cat) => {
        const catPanels = panels.filter(p => p.category === cat.key);
        return (
          <div className="rm-category" key={cat.key}>
            <h3 className="rm-category-title">
              <span className="rm-category-icon">{cat.icon}</span>
              {cat.label}
            </h3>
            <div className="rm-card-grid">
              {catPanels.map((panel) => (
                <button
                  key={panel.id}
                  className="rm-card"
                  onClick={() => setActivePanel(panel.id)}
                  aria-label={panel.label}
                >
                  <span className="rm-card-icon">{panel.icon}</span>
                  <div className="rm-card-text">
                    <span className="rm-card-title">{panel.label}</span>
                    <span className="rm-card-desc">{panel.description}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
