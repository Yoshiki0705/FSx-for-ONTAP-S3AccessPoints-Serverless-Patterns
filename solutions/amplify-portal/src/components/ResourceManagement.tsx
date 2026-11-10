import { useState, useEffect } from "react";
import { useTranslation } from "../i18n";
import { Icon, type IconName } from "./Icon";
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
import { SvmSelector } from "./admin/SvmSelector";
import { PlatformSelector } from "./admin/PlatformSelector";
import { FlexCacheManager } from "./admin/FlexCacheManager";
import { FlexCloneManager } from "./admin/FlexCloneManager";
import { SnapMirrorStatus } from "./admin/SnapMirrorStatus";
import { LocalUserManager } from "./admin/LocalUserManager";
import { NameMappingManager } from "./admin/NameMappingManager";
import { VscanManager } from "./admin/VscanManager";
import { FPolicyManager } from "./admin/FPolicyManager";
import { AuditManager } from "./admin/AuditManager";
import { PeeringManager } from "./admin/PeeringManager";
import { SvmManager } from "./admin/SvmManager";
import { ObjectStoreBucketManager } from "./admin/ObjectStoreBucketManager";
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
  | "audit"
  | "objectStore"
  | "peering"
  | "svm"
  | "cluster";

interface PanelDef {
  id: AdminPanel;
  icon: IconName;
  label: string;
  description: string;
  category: "storage" | "access" | "protection" | "services" | "cluster";
}

interface ResourceManagementProps {
  aiSettings?: { aiAgentEnabled: boolean; aiSearchEnabled: boolean };
  onAiSettingsChange?: (settings: { aiAgentEnabled: boolean; aiSearchEnabled: boolean }) => void;
}

/**
 * Panel another view asked us to open, if any.
 *
 * A pure read, so it is safe for React to call it more than once (StrictMode
 * double-invokes state initialisers). The value is cleared separately.
 */
function readRedirectPanel(): AdminPanel | null {
  if (typeof sessionStorage === "undefined") return null;
  return (sessionStorage.getItem("rm-panel") as AdminPanel | null) ?? null;
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
  // Auto-open sub-panel if redirected from Lock panel. Reading the handoff in
  // the initialiser means the first render already shows the right panel; an
  // effect would render the grid first and then replace it.
  const [activePanel, setActivePanel] = useState<AdminPanel | null>(
    () => readRedirectPanel(),
  );

  // The handoff has been consumed, so clear it: a later visit starts on the
  // grid. Clearing is not state, so it stays in an effect.
  useEffect(() => {
    if (typeof sessionStorage !== "undefined") sessionStorage.removeItem("rm-panel");
  }, []);

  const panels: PanelDef[] = [
    // Storage
    { id: "volumes", icon: "hard-drive", label: t("rmVolumes"), description: t("rmVolumesDesc"), category: "storage" },
    { id: "qtrees", icon: "git-branch", label: t("rmQtrees"), description: t("rmQtreesDesc"), category: "storage" },
    { id: "quotas", icon: "bar-chart", label: t("rmQuotas"), description: t("rmQuotasDesc"), category: "storage" },
    { id: "efficiency", icon: "trending-up", label: t("rmEfficiency"), description: t("rmEfficiencyDesc"), category: "storage" },
    { id: "flexCache", icon: "zap", label: t("rmFlexCache"), description: t("rmFlexCacheDesc"), category: "storage" },
    { id: "flexClone", icon: "copy", label: t("rmFlexClone"), description: t("rmFlexCloneDesc"), category: "storage" },
    { id: "objectStore", icon: "archive", label: t("rmObjectStore"), description: t("rmObjectStoreDesc"), category: "storage" },
    // Access Control
    { id: "exportPolicies", icon: "clipboard-list", label: t("rmExportPolicies"), description: t("rmExportPoliciesDesc"), category: "access" },
    { id: "cifsShares", icon: "folder", label: t("rmCifsShares"), description: t("rmCifsSharesDesc"), category: "access" },
    { id: "qos", icon: "zap", label: t("rmQosPolicies"), description: t("rmQosPoliciesDesc"), category: "access" },
    { id: "localUsers", icon: "user", label: t("rmLocalUsers"), description: t("rmLocalUsersDesc"), category: "access" },
    { id: "nameMapping", icon: "link", label: t("rmNameMapping"), description: t("rmNameMappingDesc"), category: "access" },
    // Protection
    { id: "arpAdmin", icon: "shield", label: t("rmArpAdmin"), description: t("rmArpAdminDesc"), category: "protection" },
    { id: "snapshotAdmin", icon: "camera", label: t("rmSnapshotAdmin"), description: t("rmSnapshotAdminDesc"), category: "protection" },
    { id: "snaplock", icon: "lock", label: t("rmSnaplock"), description: t("rmSnaplockDesc"), category: "protection" },
    { id: "snapMirror", icon: "refresh", label: t("rmSnapMirror"), description: t("rmSnapMirrorDesc"), category: "protection" },
    { id: "vscan", icon: "bug", label: t("rmVscan"), description: t("rmVscanDesc"), category: "protection" },
    { id: "fpolicy", icon: "file-text", label: t("rmFpolicy"), description: t("rmFpolicyDesc"), category: "protection" },
    { id: "audit", icon: "file-text", label: t("rmAudit"), description: t("rmAuditDesc"), category: "protection" },
    // Cluster — the areas the AWS console does not cover
    { id: "peering", icon: "link", label: t("rmPeering"), description: t("rmPeeringDesc"), category: "cluster" },
    { id: "svm", icon: "building", label: t("rmSvm"), description: t("rmSvmDesc"), category: "cluster" },
    { id: "cluster", icon: "monitor", label: t("rmCluster"), description: t("rmClusterDesc"), category: "cluster" },
    // AI & Services
    { id: "aiSettings", icon: "bot", label: t("rmAiSettings"), description: t("rmAiSettingsDesc"), category: "services" },
  ];

  const categories: ReadonlyArray<{ key: PanelDef["category"]; label: string; icon: IconName }> = [
    { key: "storage", label: t("rmCatStorage"), icon: "database" },
    { key: "access", label: t("rmCatAccess"), icon: "lock-keyhole" },
    { key: "protection", label: t("rmCatProtection"), icon: "shield" },
    { key: "cluster", label: t("rmCatCluster"), icon: "monitor" },
    { key: "services", label: t("rmCatServices"), icon: "bot" },
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
          <h2>{current && <Icon name={current.icon} className="icon-lead" />}{current?.label}</h2>
          <PlatformSelector />
          <SvmSelector />
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
          {activePanel === "audit" && <AuditManager />}
          {activePanel === "objectStore" && <ObjectStoreBucketManager />}
          {activePanel === "peering" && <PeeringManager />}
          {activePanel === "svm" && <SvmManager />}
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
        <h2><Icon name="wrench" className="icon-lead" />{t("rmTitle")}</h2>
        <span className="rm-badge">{t("rmAdminOnly")}</span>
        <PlatformSelector />
          <SvmSelector />
      </div>

      <StorageDashboard onNavigate={(panel) => setActivePanel(panel as AdminPanel)} />

      {categories.map((cat) => {
        const catPanels = panels.filter(p => p.category === cat.key);
        return (
          <div className="rm-category" key={cat.key}>
            <h3 className="rm-category-title">
              <span className="rm-category-icon"><Icon name={cat.icon} /></span>
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
                  <span className="rm-card-icon"><Icon name={panel.icon} /></span>
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
