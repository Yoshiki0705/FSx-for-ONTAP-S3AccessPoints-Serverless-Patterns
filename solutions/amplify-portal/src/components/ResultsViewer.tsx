import { useQuery } from "@tanstack/react-query";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { FlexCloneStatus } from "./FlexCloneStatus";
import { useTranslation } from "../i18n";
import { errorMessage } from "../lib/portalQuery";

const client = generateClient<Schema>();

interface ResultsViewerProps {
  executionArn: string | null;
  inputPrefix?: string;
  onNavigateToFolder?: (prefix: string) => void;
}

interface JobResult {
  executionArn: string;
  status: string;
  startDate: string | null;
  stopDate: string | null;
  output: Record<string, unknown> | null;
}

/**
 * Results Viewer component.
 *
 * Polls Step Functions execution status and displays:
 * - Current status (RUNNING / SUCCEEDED / FAILED / etc.)
 * - Execution timeline (start → stop)
 * - Output data (when completed)
 * - Data classification label (if present in output)
 *
 * Auto-polls every 5 seconds while status is RUNNING.
 */
export function ResultsViewer({ executionArn, inputPrefix, onNavigateToFolder }: ResultsViewerProps) {
  const { t } = useTranslation();
  // Polling is the query's own concern: refetchInterval keeps asking every 5s
  // while the execution is RUNNING and stops on its own once it is not. That
  // replaces a setInterval that had to be torn down by hand.
  const {
    data: result = null,
    isFetching: loading,
    error: queryError,
    refetch,
  } = useQuery({
    queryKey: ["jobStatus", executionArn],
    enabled: !!executionArn,
    refetchInterval: (query) =>
      query.state.data?.status === "RUNNING" ? 5000 : false,
    queryFn: async () => {
      const response = await client.queries.getJobStatus({
        executionArn: executionArn!,
      });
      if (response.errors?.length) {
        throw new Error(response.errors.map((e) => e.message).join(", "));
      }
      return response.data as unknown as JobResult;
    },
  });
  const error = errorMessage(queryError, "Failed to fetch status");
  const fetchStatus = () => void refetch();

  if (!executionArn) {
    return (
      <div className="results-viewer">
        <h2>{t("labelResults")}</h2>
        <div className="empty-state">
          {t("rvNoActiveJob")}
        </div>
      </div>
    );
  }

  const statusColor = (status: string) => {
    switch (status) {
      case "RUNNING": return "status-running";
      case "SUCCEEDED": return "status-succeeded";
      case "FAILED": return "status-failed";
      case "TIMED_OUT": return "status-failed";
      case "ABORTED": return "status-aborted";
      default: return "";
    }
  };

  const dataClassification = result?.output?.dataClassification as string | undefined;

  return (
    <div className="results-viewer">
      <h2>{t("labelResults")}</h2>

      {inputPrefix && onNavigateToFolder && (
        <nav className="results-breadcrumb" aria-label={t("rvFolderAria")}>
          <span>Processed: </span>
          <button
            className="breadcrumb-link"
            onClick={() => onNavigateToFolder(inputPrefix)}
            title={`Navigate to ${inputPrefix}`}
          >
            📂 /{inputPrefix}
          </button>
        </nav>
      )}

      {error && <div className="error-message">{error}</div>}

      {result && (
        <div className="result-card">
          <div className="result-header" aria-live="polite" aria-atomic="true">
            <span className={`status-badge ${statusColor(result.status)}`} role="status">
              {result.status}
            </span>
            {result.status === "RUNNING" && (
              <span className="polling-indicator">{t("rvPolling")}</span>
            )}
          </div>

          <dl className="result-details">
            <dt>{t("rvExecutionArn")}</dt>
            <dd className="arn">{result.executionArn}</dd>

            <dt>{t("labelStarted")}</dt>
            <dd>{result.startDate ? new Date(parseFloat(result.startDate) * 1000).toLocaleString() : "-"}</dd>

            <dt>{t("labelCompleted")}</dt>
            <dd>{result.stopDate ? new Date(parseFloat(result.stopDate) * 1000).toLocaleString() : "-"}</dd>

            {dataClassification && (
              <>
                <dt>{t("rvDataClassification")}</dt>
                <dd className={`classification classification-${dataClassification.toLowerCase()}`}>
                  {dataClassification}
                </dd>
              </>
            )}
          </dl>

          {result.output && result.status === "SUCCEEDED" && (
            <>
              {result.output.flexClone && (
                <FlexCloneStatus cloneInfo={result.output.flexClone as Record<string, string>} />
              )}
              <details className="result-output">
                <summary>{t("rvOutputData")}</summary>
                <pre>{JSON.stringify(result.output, null, 2)}</pre>
              </details>
            </>
          )}

          <button onClick={fetchStatus} disabled={loading} className="refresh-btn">
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      )}

      {loading && !result && <div className="loading">{t("rvLoadingStatus")}</div>}
    </div>
  );
}
