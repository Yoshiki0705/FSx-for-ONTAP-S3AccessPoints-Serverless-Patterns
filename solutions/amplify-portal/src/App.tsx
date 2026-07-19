import { useState } from "react";
import { useAuthenticator } from "@aws-amplify/ui-react";
import { FileExplorer } from "./components/FileExplorer";
import { JobSubmitForm } from "./components/JobSubmitForm";
import { ResultsViewer } from "./components/ResultsViewer";
import { JobHistory } from "./components/JobHistory";
import { LoadingSkeleton } from "./components/LoadingSkeleton";
import { AiPanel } from "./components/AiPanel";
import { AthenaQueryPanel } from "./components/AthenaQueryPanel";

type View = "files" | "submit" | "results" | "history" | "analytics";

const VIEWS: { id: View; label: string }[] = [
  { id: "files", label: "Files" },
  { id: "submit", label: "Process" },
  { id: "results", label: "Results" },
  { id: "history", label: "History" },
  { id: "analytics", label: "Analytics" },
];

/**
 * Main application shell.
 *
 * Three-panel navigation:
 * - Files: Browse FSx for ONTAP volume contents via S3 AP
 * - Submit: Trigger processing workflows (Step Functions)
 * - Results: View workflow execution status and outputs
 */
function App() {
  const [currentView, setCurrentView] = useState<View>("files");
  const [selectedPrefix, setSelectedPrefix] = useState("");
  const [activeJobArn, setActiveJobArn] = useState<string | null>(null);
  const [selectedFileKey, setSelectedFileKey] = useState<string | null>(null);
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const { user, signOut, authStatus } = useAuthenticator();

  // Show skeleton while auth is resolving (prevents blank flash)
  if (authStatus !== "authenticated") {
    return <LoadingSkeleton />;
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>FSx for ONTAP File Portal</h1>
        <nav className="app-nav" role="tablist" aria-label="Portal navigation">
          {VIEWS.map((view) => (
            <button
              key={view.id}
              role="tab"
              aria-selected={currentView === view.id}
              aria-controls={`panel-${view.id}`}
              className={currentView === view.id ? "active" : ""}
              onClick={() => setCurrentView(view.id)}
            >
              {view.label}
            </button>
          ))}
        </nav>
        <div className="user-info">
          <span>{user?.signInDetails?.loginId}</span>
          <button onClick={signOut} className="sign-out" aria-label="Sign out">
            Sign Out
          </button>
        </div>
      </header>

      <main className="app-main">
        <div id="panel-files" role="tabpanel" aria-labelledby="tab-files" hidden={currentView !== "files"}>
          {currentView === "files" && (
            <>
              <FileExplorer
                onSelectPrefix={(prefix) => {
                  setSelectedPrefix(prefix);
                  setCurrentView("submit");
                }}
                onFileSelect={(key, name) => {
                  setSelectedFileKey(key);
                  setSelectedFileName(name);
                }}
              />
              <AiPanel
                selectedFileKey={selectedFileKey}
                selectedFileName={selectedFileName}
              />
            </>
          )}
        </div>
        <div id="panel-submit" role="tabpanel" aria-labelledby="tab-submit" hidden={currentView !== "submit"}>
          {currentView === "submit" && (
            <JobSubmitForm
              initialPrefix={selectedPrefix}
              onJobStarted={(arn) => {
                setActiveJobArn(arn);
                setCurrentView("results");
              }}
            />
          )}
        </div>
        <div id="panel-results" role="tabpanel" aria-labelledby="tab-results" hidden={currentView !== "results"}>
          {currentView === "results" && (
            <ResultsViewer
              executionArn={activeJobArn}
              inputPrefix={selectedPrefix}
              onNavigateToFolder={(prefix) => {
                setSelectedPrefix(prefix);
                setCurrentView("files");
              }}
            />
          )}
        </div>
        <div id="panel-history" role="tabpanel" aria-labelledby="tab-history" hidden={currentView !== "history"}>
          {currentView === "history" && (
            <JobHistory
              onSelectExecution={(arn) => {
                setActiveJobArn(arn);
                setCurrentView("results");
              }}
            />
          )}
        </div>
        <div id="panel-analytics" role="tabpanel" aria-labelledby="tab-analytics" hidden={currentView !== "analytics"}>
          {currentView === "analytics" && <AthenaQueryPanel />}
        </div>
      </main>
    </div>
  );
}

export default App;
