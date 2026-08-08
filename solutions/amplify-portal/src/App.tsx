import { useState, useEffect } from "react";
import { useAuthenticator } from "@aws-amplify/ui-react";
import { FileExplorer } from "./components/FileExplorer";
import { JobSubmitForm } from "./components/JobSubmitForm";
import { ResultsViewer } from "./components/ResultsViewer";
import { JobHistory } from "./components/JobHistory";
import { LoadingSkeleton } from "./components/LoadingSkeleton";
import { AiPanel } from "./components/AiPanel";
import { AthenaQueryPanel } from "./components/AthenaQueryPanel";
import { StorageBrowserTab } from "./components/StorageBrowserTab";
import { FavoritesView, isFolderKey } from "./components/Favorites";
import { RecentFiles } from "./components/RecentFiles";
import { FolderWatch } from "./components/FolderWatch";
import { VersionHistory } from "./components/VersionHistory";
import { AuditLog } from "./components/AuditLog";
import { ArpStatus } from "./components/ArpStatus";
import { SnaplockStatus } from "./components/SnaplockStatus";
import { ResourceManagement } from "./components/ResourceManagement";
import { AgentChat } from "./components/AgentChat";
import { AgentDirectory } from "./components/AgentDirectory";
import { AgentCreator } from "./components/AgentCreator";
import { AgentTeams } from "./components/AgentTeams";
import { SemanticSearch } from "./components/SemanticSearch";
import { LanguageSwitcher } from "./components/LanguageSwitcher";
import { WelcomeModal } from "./components/WelcomeModal";
import { useTranslation } from "./i18n";
import { useStorageAdmin } from "./hooks/useStorageAdmin";
import { dispatch } from "./lib/dispatch";
import { portalSettings } from "./portal-settings";

import type { TranslationKeys } from "./i18n";

type Section =
  | "files" | "favorites" | "recent" | "watch" | "upload"
  | "process" | "agent" | "search" | "history" | "analytics"
  | "snapshots" | "arp" | "lock"
  | "versions" | "audit" | "resources" | "agentDir";

const NAV_ITEMS: { id: Section; icon: string; labelKey: TranslationKeys; group: "browse" | "actions" | "protection" | "admin" }[] = [
  // Browse group
  { id: "files", icon: "📂", labelKey: "navAllFiles", group: "browse" },
  { id: "favorites", icon: "⭐", labelKey: "navFavorites", group: "browse" },
  { id: "recent", icon: "🕐", labelKey: "navRecent", group: "browse" },
  { id: "watch", icon: "🔔", labelKey: "navFolderWatch", group: "browse" },
  { id: "upload", icon: "📤", labelKey: "navUpload", group: "browse" },
  // AI & Processing group
  { id: "process", icon: "⚡", labelKey: "navAiProcessing", group: "actions" },
  { id: "agent", icon: "🤖", labelKey: "navAgent", group: "actions" },
  { id: "search", icon: "🔍", labelKey: "navSearch", group: "actions" },
  { id: "history", icon: "📋", labelKey: "navJobHistory", group: "actions" },
  { id: "analytics", icon: "📊", labelKey: "navAnalytics", group: "actions" },
  { id: "agentDir", icon: "🗂️", labelKey: "navAgentDir", group: "actions" },
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

/** Sections that may appear in the URL hash. */
const SECTIONS: Section[] = ["files","favorites","recent","upload","process","agent","search","history","analytics","snapshots","arp","lock","versions","audit","resources","agentDir"];

/** The hash without its leading "#", if it names a section. */
function sectionFromHash(): Section | null {
  const hash = window.location.hash.replace("#", "");
  return SECTIONS.includes(hash as Section) ? (hash as Section) : null;
}

/** Folder holding the given object key, as a prefix with a trailing slash. */
function parentPrefixOf(fileKey: string): string {
  const parts = fileKey.split("/");
  parts.pop();
  return parts.length > 0 ? parts.join("/") + "/" : "";
}

function App() {
  // Navigation state is persisted in the URL hash so a refresh restores the section.
  const [activeSection, setActiveSection] = useState<Section>(() => sectionFromHash() ?? "files");

  // State is the source of truth; the hash mirrors it. Writing the hash from the
  // click handler instead would mutate a value outside the component during the
  // render pass React attributes it to.
  useEffect(() => {
    if (sectionFromHash() !== activeSection) {
      window.location.hash = activeSection;
    }
  }, [activeSection]);

  // Listen for hash changes from other components (Lock panel navigation) and from
  // the browser's back/forward buttons. No activeSection dependency: setting state
  // to its current value is a no-op, so the guard the comparison used to provide is
  // not needed, and the listener no longer detaches on every navigation.
  useEffect(() => {
    const onHashChange = () => {
      const section = sectionFromHash();
      if (section) setActiveSection(section);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const [selectedPrefix, setSelectedPrefix] = useState("");
  const [prefixNonce, setPrefixNonce] = useState(0);
  const [activeJobArn, setActiveJobArn] = useState<string | null>(null);
  const [selectedFileKey, setSelectedFileKey] = useState<string | null>(null);

  /** Show the file explorer at the given folder, even if it is already there. */
  const openInFiles = (prefix: string) => {
    setSelectedPrefix(prefix);
    setPrefixNonce((n) => n + 1);
    setActiveSection("files");
  };
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const { user, signOut, authStatus } = useAuthenticator();
  const { t } = useTranslation();

  // --- Admin-controlled AI feature gate ---
  // Query DynamoDB portal settings on mount. Falls back to compile-time portalSettings.
  const [aiAgentEnabled, setAiAgentEnabled] = useState(portalSettings.aiAgentEnabled);
  const [aiSearchEnabled, setAiSearchEnabled] = useState(portalSettings.aiAgentEnabled);
  // Carried down to AgentChat. These two used to be written by the admin panel and
  // read by nothing, so both switches were decoration: turning image input off left
  // the paperclip in place, and turning history off kept saving sessions.
  const [aiMultimodalEnabled, setAiMultimodalEnabled] = useState(false);
  const [chatHistoryEnabled, setChatHistoryEnabled] = useState(false);
  // Folder watch depends on a publisher outside the portal (FPolicy or Transfer
  // Family emitting to EventBridge), so it is off until an admin says that
  // publisher exists. Defaulting it on would show an inbox that can never fill.
  const [folderWatchEnabled, setFolderWatchEnabled] = useState(false);
  const isStorageAdmin = useStorageAdmin();
  // Set when the directory or the team list hands one over, and carried into the
  // chat section. Lives here rather than in AgentChat because the two sections are
  // siblings and the handover crosses between them.
  const [runTarget, setRunTarget] = useState<RunTarget | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadAiSettings() {
      try {
        const response = await dispatch("adminQuery", { action: "getPortalSettings" });
        if (cancelled) return;
        const parsed = response.data
          ? (typeof response.data === "string" ? JSON.parse(response.data) : response.data)
          : null;
        if (parsed?.settings) {
          setAiAgentEnabled(parsed.settings.aiAgentEnabled === true);
          setAiSearchEnabled(parsed.settings.aiSearchEnabled === true);
          setAiMultimodalEnabled(parsed.settings.aiMultimodalEnabled === true);
          setChatHistoryEnabled(parsed.settings.chatHistoryEnabled === true);
          setFolderWatchEnabled(parsed.settings.folderWatchEnabled === true);
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
  if (!aiAgentEnabled) hiddenSections.add("agentDir");
  if (!folderWatchEnabled) hiddenSections.add("watch");
  // Resource Management is the only section whose every panel needs the
  // storage-admin group. It was shown to everyone, so a non-admin got the card
  // grid and an authorization error from each of the twenty panels behind it.
  // `null` means the session has not resolved yet; hide it until it has rather
  // than show the section and take it away.
  if (isStorageAdmin !== true) hiddenSections.add("resources");
  // Analytics runs whatever SQL is typed into it, so runAthenaQuery now requires the
  // same group. Hidden here for the same reason as above: without this the section
  // stays in the sidebar and every query comes back as an authorization error.
  if (isStorageAdmin !== true) hiddenSections.add("analytics");

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
            initialPrefix={selectedPrefix}
            prefixNonce={prefixNonce}
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
            onNavigate={(favoriteKey) => {
              // A folder favorite opens that folder; a file favorite opens the
              // folder containing it.
              openInFiles(
                isFolderKey(favoriteKey)
                  ? favoriteKey
                  : parentPrefixOf(favoriteKey)
              );
            }}
          />
        )}
        {activeSection === "recent" && (
          <RecentFiles
            onFileSelect={(fileKey) => {
              setSelectedFileKey(fileKey);
              setSelectedFileName(fileKey.split("/").pop() || fileKey);
              openInFiles(parentPrefixOf(fileKey));
            }}
          />
        )}
        {activeSection === "watch" && <FolderWatch />}
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
        {activeSection === "agent" && (aiAgentEnabled ? (
          <AgentChat
            multimodalEnabled={aiMultimodalEnabled}
            chatHistoryEnabled={chatHistoryEnabled}
            runTarget={runTarget}
            onClearRunTarget={() => setRunTarget(null)}
          />
        ) : <AgentDisabled />)}
        {activeSection === "search" && (aiSearchEnabled ? (
          <SemanticSearch
            onNavigateToFile={(fileKey) => openInFiles(parentPrefixOf(fileKey))}
          />
        ) : <AgentDisabled />)}
        {activeSection === "history" && (
          <>
            {activeJobArn && (
              <ResultsViewer
                executionArn={activeJobArn}
                inputPrefix={selectedPrefix}
                onNavigateToFolder={(prefix) => openInFiles(prefix)}
              />
            )}
            <JobHistory
              onSelectExecution={(arn) => setActiveJobArn(arn)}
            />
          </>
        )}
        {activeSection === "versions" && <VersionHistory mode="diff" />}
        {activeSection === "audit" && <AuditLog />}
        {/* Guarded again here, not only in the nav: sections are reachable by URL
            hash, and hiding the button alone left a non-admin on a blank page. */}
        {activeSection === "analytics" && (isStorageAdmin === true ? (
          <AthenaQueryPanel />
        ) : isStorageAdmin === false ? <AdminOnly /> : <LoadingSkeleton />)}

        {/* Data Protection sections */}
        {activeSection === "snapshots" && <VersionHistory mode="browse" />}
        {activeSection === "lock" && <SnaplockStatus />}
        {activeSection === "arp" && <ArpStatus />}
        {/* Guarded again here, not only in the nav: the section is reachable by
            URL hash, and hiding the button alone left a non-admin on a blank page. */}
        {activeSection === "resources" && (isStorageAdmin === true ? (
          <ResourceManagement
            aiSettings={{ aiAgentEnabled, aiSearchEnabled }}
            onAiSettingsChange={(s) => { setAiAgentEnabled(s.aiAgentEnabled); setAiSearchEnabled(s.aiSearchEnabled); }}
          />
        ) : isStorageAdmin === false ? <AdminOnly /> : <LoadingSkeleton />)}
        {activeSection === "agentDir" && (
          <AgentDirectoryPage
            onRun={(target) => {
              setRunTarget(target);
              setActiveSection("agent");
            }}
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

/** A stored agent or team the chat should run instead of a built-in mode. */
type RunTarget = { kind: "agent" | "team"; id: string; name: string };

/** Agent Directory Page — combines Directory, Creator, and Teams */
function AgentDirectoryPage({ onRun }: { onRun: (target: RunTarget) => void }) {
  const { t } = useTranslation();
  const [view, setView] = useState<"directory" | "creator" | "teams">("directory");

  return (
    <div>
      {/* Tab bar */}
      <div className="agent-dir-tabs">
        <button className={`agent-dir-tab ${view === "directory" ? "active" : ""}`} onClick={() => setView("directory")}>
          🗂️ {t("agentDirTitle")}
        </button>
        <button className={`agent-dir-tab ${view === "teams" ? "active" : ""}`} onClick={() => setView("teams")}>
          🧩 {t("teamsTitle")}
        </button>
      </div>

      {view === "directory" && (
        <AgentDirectory
          onCreateAgent={() => setView("creator")}
          onRunAgent={(id, name) => onRun({ kind: "agent", id, name })}
        />
      )}
      {view === "creator" && (
        <AgentCreator
          onCreated={() => setView("directory")}
          onCancel={() => setView("directory")}
        />
      )}
      {view === "teams" && (
        <AgentTeams onSelectTeam={(id, name) => onRun({ kind: "team", id, name })} />
      )}
    </div>
  );
}

/**
 * Shown when a section is reached by URL but the account is not a storage admin.
 *
 * The same styling as the AI-disabled panel: from the user's point of view both are
 * "this section is not available to you", and the reason differs only in who can
 * change it.
 */
function AdminOnly() {
  const { t } = useTranslation();
  return (
    <div className="agent-disabled">
      <div className="agent-disabled-icon">🔒</div>
      <h3>{t("adminOnlyTitle")}</h3>
      <p>{t("adminOnlyDesc")}</p>
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
