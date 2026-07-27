import { useState, useEffect } from "react";
import { useAuthenticator } from "@aws-amplify/ui-react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../amplify/data/resource";
import { FileExplorer } from "./components/FileExplorer";
import { JobSubmitForm } from "./components/JobSubmitForm";
import { ResultsViewer } from "./components/ResultsViewer";
import { JobHistory } from "./components/JobHistory";
import { LoadingSkeleton } from "./components/LoadingSkeleton";
import { AiPanel } from "./components/AiPanel";
import { AthenaQueryPanel } from "./components/AthenaQueryPanel";
import { StorageBrowserTab } from "./components/StorageBrowserTab";
import { FavoritesView } from "./components/Favorites";
import { RecentFiles } from "./components/RecentFiles";
import { VersionHistory } from "./components/VersionHistory";
import { AuditLog } from "./components/AuditLog";
import { ArpStatus } from "./components/ArpStatus";
import { SnaplockStatus } from "./components/SnaplockStatus";
import { ResourceManagement } from "./components/ResourceManagement";
import { AgentChat } from "./components/AgentChat";
import { SemanticSearch } from "./components/SemanticSearch";
import { LanguageSwitcher } from "./components/LanguageSwitcher";
import { WelcomeModal } from "./components/WelcomeModal";
import { useTranslation } from "./i18n";
import { portalSettings } from "./portal-settings";

import type { TranslationKeys } from "./i18n";

const appClient = generateClient<Schema>();

type Section =
  | "files" | "favorites" | "recent" | "upload"
  | "process" | "agent" | "search" | "history" | "analytics"
  | "snapshots" | "arp" | "lock"
  | "versions" | "audit" | "resources";

const NAV_ITEMS: { id: Section; icon: string; labelKey: TranslationKeys; group: "browse" | "actions" | "protection" | "admin" }[] = [
  // Browse group
  { id: "files", icon: "📂", labelKey: "navAllFiles", group: "browse" },
  { id: "favorites", icon: "⭐", labelKey: "navFavorites", group: "browse" },
  { id: "recent", icon: "🕐", labelKey: "navRecent", group: "browse" },
  { id: "upload", icon: "📤", labelKey: "navUpload", group: "browse" },
  // AI & Processing group
  { id: "process", icon: "⚡", labelKey: "navAiProcessing", group: "actions" },
  { id: "agent", icon: "🤖", labelKey: "navAgent", group: "actions" },
  { id: "search", icon: "🔍", labelKey: "navSearch", group: "actions" },
  { id: "history", icon: "📋", labelKey: "navJobHistory", group: "actions" },
  { id: "analytics", icon: "📊", labelKey: "navAnalytics", group: "actions" },
  // Data Protection group
  { id: "snapshots", icon: "📸", labelKey: "navSnapshots", group: "protection" },
  { id: "lock", icon: "🔒", labelKey: "navLock", group: "protection" },
  { id: "arp", icon: "🛡️", labelKey: "navArp", group: "protection" },
  // Admin group
  { id: "resources", icon: "🔧", labelKey: "navResources", group: "admin" },
  { id: "versions", icon: "🔄", labelKey: "navVersionDiff", group: "admin" },
  { id: "audit", icon: "🔍", labelKey: "navAuditTrail", group: "admin" },
];

const GROUP_LABELS: Record<string, TranslationKeys> = {
  browse: "groupBrowse",
  actions: "groupAiProcessing",
  protection: "groupDataProtection",
  admin: "groupAdmin",
};

/**
 * FSx for ONTAP File Portal — Main Application Shell
 *
 * Layout follows modern file management UX patterns (Google Drive, Box, SharePoint):
 * - Left sidebar: Section navigation grouped by purpose
 * - Main content: Active section (file browser, upload, processing, etc.)
 * - Right panel: Contextual AI assistant (appears when file is selected)
 *
 * Design principles:
 * - Sidebar navigation (not tabs) — scalable to many sections
 * - Progressive disclosure — AI panel only appears when relevant
 * - Contextual actions — file operations appear on hover/selection
 * - Responsive — sidebar collapses on mobile
 */
function App() {
  // Persist navigation state in URL hash for refresh resilience
  const getInitialSection = (): Section => {
    const hash = window.location.hash.replace("#", "");
    const valid: Section[] = ["files","favorites","recent","upload","process","agent","search","history","analytics","snapshots","arp","lock","versions","audit","resources"];
    return valid.includes(hash as Section) ? (hash as Section) : "files";
  };

  const [activeSection, setActiveSectionRaw] = useState<Section>(getInitialSection);

  const setActiveSection = (section: Section) => {
    setActiveSectionRaw(section);
    window.location.hash = section;
  };

  // Listen for hash changes from other components (Lock panel navigation)
  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.replace("#", "");
      const valid: Section[] = ["files","favorites","recent","upload","process","agent","search","history","analytics","snapshots","arp","lock","versions","audit","resources"];
      if (valid.includes(hash as Section) && hash !== activeSection) {
        setActiveSectionRaw(hash as Section);
      }
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, [activeSection]);

  const [selectedPrefix, setSelectedPrefix] = useState("");
  const [activeJobArn, setActiveJobArn] = useState<string | null>(null);
  const [selectedFileKey, setSelectedFileKey] = useState<string | null>(null);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const { user, signOut, authStatus } = useAuthenticator();
  const { t } = useTranslation();

  // --- Admin-controlled AI feature gate ---
  // Query DynamoDB portal settings on mount. Falls back to compile-time portalSettings.
  const [aiAgentEnabled, setAiAgentEnabled] = useState(portalSettings.aiAgentEnabled);
  const [aiSearchEnabled, setAiSearchEnabled] = useState(portalSettings.aiAgentEnabled);

  useEffect(() => {
    let cancelled = false;
    async function loadAiSettings() {
      try {
        const response = await appClient.queries.adminQuery({
          action: "getPortalSettings",
          params: JSON.stringify({}),
        });
        if (cancelled) return;
        const parsed = response.data
          ? (typeof response.data === "string" ? JSON.parse(response.data) : response.data)
          : null;
        if (parsed?.settings) {
          setAiAgentEnabled(parsed.settings.aiAgentEnabled === true);
          setAiSearchEnabled(parsed.settings.aiSearchEnabled === true);
        }
      } catch {
        // Non-admin users may get auth error — fall back to compile-time default
      }
    }
    loadAiSettings();
    return () => { cancelled = true; };
  }, []);

  // Sections hidden when AI is disabled
  const hiddenSections: Set<Section> = new Set();
  if (!aiAgentEnabled) hiddenSections.add("agent");
  if (!aiSearchEnabled) hiddenSections.add("search");

  if (authStatus !== "authenticated") {
    return <LoadingSkeleton />;
  }

  const showAiPanel = selectedFileKey && activeSection === "files";

  return (
    <div className={`portal-layout ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <WelcomeModal />
      {/* Top bar: Search + Notifications + User */}
      <header className="portal-topbar">
        <button
          className="sidebar-toggle"
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          aria-label={sidebarCollapsed ? t("expandNav") : t("collapseNav")}
        >
          {sidebarCollapsed ? "☰" : "✕"}
        </button>
        <h1 className="portal-title">{t("appTitle")}</h1>
        <div className="topbar-spacer" />
        <LanguageSwitcher />
        <div className="topbar-user">
          <span className="user-email">{user?.signInDetails?.loginId}</span>
          <button onClick={signOut} className="sign-out-btn">
            {t("signOut")}
          </button>
        </div>
      </header>

      {/* Left sidebar: Navigation */}
      <nav className="portal-sidebar" aria-label="Main navigation">
        {(["browse", "actions", "protection", "admin"] as const).map((group) => (
          <div className="sidebar-section" key={group}>
            <span className="sidebar-group-label">{t(GROUP_LABELS[group])}</span>
            {NAV_ITEMS.filter((n) => n.group === group && !hiddenSections.has(n.id)).map((item) => (
              <button
                key={item.id}
                className={`sidebar-item ${activeSection === item.id ? "active" : ""}`}
                onClick={() => setActiveSection(item.id)}
                aria-current={activeSection === item.id ? "page" : undefined}
              >
                <span className="sidebar-icon">{item.icon}</span>
                <span className="sidebar-label">{t(item.labelKey)}</span>
              </button>
            ))}
          </div>
        ))}
      </nav>

      {/* Main content area */}
      <main className={`portal-main ${showAiPanel ? "with-panel" : ""}`}>
        {activeSection === "files" && (
          <FileExplorer
            onSelectPrefix={(prefix) => {
              setSelectedPrefix(prefix);
              setActiveSection("process");
            }}
            onFileSelect={(key, name) => {
              setSelectedFileKey(key);
              setSelectedFileName(name);
            }}
          />
        )}
        {activeSection === "favorites" && (
          <FavoritesView
            onNavigate={(fileKey) => {
              const parts = fileKey.split("/");
              parts.pop();
              setSelectedPrefix(parts.length > 0 ? parts.join("/") + "/" : "");
              setActiveSection("files");
            }}
          />
        )}
        {activeSection === "recent" && (
          <RecentFiles
            onFileSelect={(fileKey) => {
              setSelectedFileKey(fileKey);
              setSelectedFileName(fileKey.split("/").pop() || fileKey);
              setActiveSection("files");
            }}
          />
        )}
        {activeSection === "upload" && <StorageBrowserTab />}
        {activeSection === "process" && (
          <JobSubmitForm
            initialPrefix={selectedPrefix}
            onJobStarted={(arn) => {
              setActiveJobArn(arn);
              setActiveSection("history");
            }}
          />
        )}
        {activeSection === "agent" && (aiAgentEnabled ? <AgentChat /> : <AgentDisabled />)}
        {activeSection === "search" && (aiSearchEnabled ? (
          <SemanticSearch
            onNavigateToFile={(fileKey) => {
              const parts = fileKey.split("/");
              parts.pop();
              setSelectedPrefix(parts.length > 0 ? parts.join("/") + "/" : "");
              setActiveSection("files");
            }}
          />
        ) : <AgentDisabled />)}
        {activeSection === "history" && (
          <>
            {activeJobArn && (
              <ResultsViewer
                executionArn={activeJobArn}
                inputPrefix={selectedPrefix}
                onNavigateToFolder={(prefix) => {
                  setSelectedPrefix(prefix);
                  setActiveSection("files");
                }}
              />
            )}
            <JobHistory
              onSelectExecution={(arn) => setActiveJobArn(arn)}
            />
          </>
        )}
        {activeSection === "versions" && <VersionHistory />}
        {activeSection === "audit" && <AuditLog />}
        {activeSection === "analytics" && <AthenaQueryPanel />}

        {/* Data Protection sections */}
        {activeSection === "snapshots" && <VersionHistory />}
        {activeSection === "lock" && <SnaplockStatus />}
        {activeSection === "arp" && <ArpStatus />}
        {activeSection === "resources" && (
          <ResourceManagement
            aiSettings={{ aiAgentEnabled, aiSearchEnabled }}
            onAiSettingsChange={(s) => { setAiAgentEnabled(s.aiAgentEnabled); setAiSearchEnabled(s.aiSearchEnabled); }}
          />
        )}
        {/* End of Data Protection sections */}
      </main>

      {/* Right panel: AI Assistant (contextual — shows when file is selected) */}
      {showAiPanel && (
        <aside className="portal-panel">
          <AiPanel
            selectedFileKey={selectedFileKey}
            selectedFileName={selectedFileName}
          />
        </aside>
      )}
    </div>
  );
}

/** Shown when AI features are disabled by admin */
function AgentDisabled() {
  const { t } = useTranslation();
  return (
    <div className="agent-disabled">
      <div className="agent-disabled-icon">🔒</div>
      <h3>{t("aiDisabledTitle")}</h3>
      <p>{t("aiDisabledDesc")}</p>
    </div>
  );
}

export default App;
