import { useState } from "react";
import { useAuthenticator } from "@aws-amplify/ui-react";
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

type Section =
  | "files" | "favorites" | "recent" | "upload"
  | "process" | "history" | "analytics"
  | "snapshots" | "arp" | "lock"
  | "versions" | "audit";

const NAV_ITEMS: { id: Section; icon: string; label: string; group: "browse" | "actions" | "protection" | "admin" }[] = [
  // Browse group
  { id: "files", icon: "📂", label: "All Files", group: "browse" },
  { id: "favorites", icon: "⭐", label: "Favorites", group: "browse" },
  { id: "recent", icon: "🕐", label: "Recent", group: "browse" },
  { id: "upload", icon: "📤", label: "Upload", group: "browse" },
  // AI & Processing group
  { id: "process", icon: "⚡", label: "AI Processing", group: "actions" },
  { id: "history", icon: "📋", label: "Job History", group: "actions" },
  { id: "analytics", icon: "📊", label: "Analytics", group: "actions" },
  // Data Protection group
  { id: "snapshots", icon: "📸", label: "Snapshots", group: "protection" },
  { id: "lock", icon: "🔒", label: "Lock", group: "protection" },
  { id: "arp", icon: "🛡️", label: "ARP/AI", group: "protection" },
  // Admin group
  { id: "versions", icon: "🔄", label: "Version Diff", group: "admin" },
  { id: "audit", icon: "🔍", label: "Audit Trail", group: "admin" },
];

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
  const [activeSection, setActiveSection] = useState<Section>("files");
  const [selectedPrefix, setSelectedPrefix] = useState("");
  const [activeJobArn, setActiveJobArn] = useState<string | null>(null);
  const [selectedFileKey, setSelectedFileKey] = useState<string | null>(null);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const { user, signOut, authStatus } = useAuthenticator();

  if (authStatus !== "authenticated") {
    return <LoadingSkeleton />;
  }

  const showAiPanel = selectedFileKey && activeSection === "files";

  return (
    <div className={`portal-layout ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      {/* Top bar: Search + Notifications + User */}
      <header className="portal-topbar">
        <button
          className="sidebar-toggle"
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          aria-label={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
        >
          {sidebarCollapsed ? "☰" : "✕"}
        </button>
        <h1 className="portal-title">File Portal</h1>
        <div className="topbar-spacer" />
        <div className="topbar-user">
          <span className="user-email">{user?.signInDetails?.loginId}</span>
          <button onClick={signOut} className="sign-out-btn">
            Sign Out
          </button>
        </div>
      </header>

      {/* Left sidebar: Navigation */}
      <nav className="portal-sidebar" aria-label="Main navigation">
        <div className="sidebar-section">
          <span className="sidebar-group-label">Browse</span>
          {NAV_ITEMS.filter((n) => n.group === "browse").map((item) => (
            <button
              key={item.id}
              className={`sidebar-item ${activeSection === item.id ? "active" : ""}`}
              onClick={() => setActiveSection(item.id)}
              aria-current={activeSection === item.id ? "page" : undefined}
            >
              <span className="sidebar-icon">{item.icon}</span>
              <span className="sidebar-label">{item.label}</span>
            </button>
          ))}
        </div>
        <div className="sidebar-section">
          <span className="sidebar-group-label">AI & Processing</span>
          {NAV_ITEMS.filter((n) => n.group === "actions").map((item) => (
            <button
              key={item.id}
              className={`sidebar-item ${activeSection === item.id ? "active" : ""}`}
              onClick={() => setActiveSection(item.id)}
              aria-current={activeSection === item.id ? "page" : undefined}
            >
              <span className="sidebar-icon">{item.icon}</span>
              <span className="sidebar-label">{item.label}</span>
            </button>
          ))}
        </div>
        <div className="sidebar-section">
          <span className="sidebar-group-label">Data Protection</span>
          {NAV_ITEMS.filter((n) => n.group === "protection").map((item) => (
            <button
              key={item.id}
              className={`sidebar-item ${activeSection === item.id ? "active" : ""}`}
              onClick={() => setActiveSection(item.id)}
              aria-current={activeSection === item.id ? "page" : undefined}
            >
              <span className="sidebar-icon">{item.icon}</span>
              <span className="sidebar-label">{item.label}</span>
            </button>
          ))}
        </div>
        <div className="sidebar-section">
          <span className="sidebar-group-label">Admin</span>
          {NAV_ITEMS.filter((n) => n.group === "admin").map((item) => (
            <button
              key={item.id}
              className={`sidebar-item ${activeSection === item.id ? "active" : ""}`}
              onClick={() => setActiveSection(item.id)}
              aria-current={activeSection === item.id ? "page" : undefined}
            >
              <span className="sidebar-icon">{item.icon}</span>
              <span className="sidebar-label">{item.label}</span>
            </button>
          ))}
        </div>
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

export default App;
