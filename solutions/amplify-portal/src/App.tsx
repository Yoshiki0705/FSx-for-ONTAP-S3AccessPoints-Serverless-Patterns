import { useState } from "react";
import { useAuthenticator } from "@aws-amplify/ui-react";
import { FileExplorer } from "./components/FileExplorer";
import { JobSubmitForm } from "./components/JobSubmitForm";
import { ResultsViewer } from "./components/ResultsViewer";

type View = "files" | "submit" | "results";

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
  const { user, signOut } = useAuthenticator();

  return (
    <div className="app">
      <header className="app-header">
        <h1>FSx for ONTAP File Portal</h1>
        <nav className="app-nav">
          <button
            className={currentView === "files" ? "active" : ""}
            onClick={() => setCurrentView("files")}
          >
            Files
          </button>
          <button
            className={currentView === "submit" ? "active" : ""}
            onClick={() => setCurrentView("submit")}
          >
            Process
          </button>
          <button
            className={currentView === "results" ? "active" : ""}
            onClick={() => setCurrentView("results")}
          >
            Results
          </button>
        </nav>
        <div className="user-info">
          <span>{user?.signInDetails?.loginId}</span>
          <button onClick={signOut} className="sign-out">
            Sign Out
          </button>
        </div>
      </header>

      <main className="app-main">
        {currentView === "files" && (
          <FileExplorer
            onSelectPrefix={(prefix) => {
              setSelectedPrefix(prefix);
              setCurrentView("submit");
            }}
          />
        )}
        {currentView === "submit" && (
          <JobSubmitForm
            initialPrefix={selectedPrefix}
            onJobStarted={(arn) => {
              setActiveJobArn(arn);
              setCurrentView("results");
            }}
          />
        )}
        {currentView === "results" && (
          <ResultsViewer executionArn={activeJobArn} />
        )}
      </main>
    </div>
  );
}

export default App;
