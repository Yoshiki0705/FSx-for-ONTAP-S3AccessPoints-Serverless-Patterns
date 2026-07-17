import { useState, useEffect, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";

const client = generateClient<Schema>();

interface ResultsViewerProps {
  executionArn: string | null;
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
export function ResultsViewer({ executionArn }: ResultsViewerProps) {
  const [result, setResult] = useState<JobResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    if (!executionArn) return;

    setLoading(true);
    setError(null);

    try {
      const response = await client.queries.getJobStatus({ executionArn });

      if (response.data) {
        setResult(response.data as unknown as JobResult);
      } else if (response.errors) {
        setError(response.errors.map((e) => e.message).join(", "));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch status");
    } finally {
      setLoading(false);
    }
  }, [executionArn]);

  // Initial fetch
  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Auto-poll while RUNNING
  useEffect(() => {
    if (result?.status !== "RUNNING") return;

    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [result?.status, fetchStatus]);

  if (!executionArn) {
    return (
      <div className="results-viewer">
        <h2>Results</h2>
        <div className="empty-state">
          No active job. Submit a processing job from the Process tab.
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
      <h2>Results</h2>

      {error && <div className="error-message">{error}</div>}

      {result && (
        <div className="result-card">
          <div className="result-header">
            <span className={`status-badge ${statusColor(result.status)}`}>
              {result.status}
            </span>
            {result.status === "RUNNING" && (
              <span className="polling-indicator">Polling every 5s...</span>
            )}
          </div>

          <dl className="result-details">
            <dt>Execution ARN</dt>
            <dd className="arn">{result.executionArn}</dd>

            <dt>Started</dt>
            <dd>{result.startDate ? new Date(parseFloat(result.startDate) * 1000).toLocaleString() : "-"}</dd>

            <dt>Completed</dt>
            <dd>{result.stopDate ? new Date(parseFloat(result.stopDate) * 1000).toLocaleString() : "-"}</dd>

            {dataClassification && (
              <>
                <dt>Data Classification</dt>
                <dd className={`classification classification-${dataClassification.toLowerCase()}`}>
                  {dataClassification}
                </dd>
              </>
            )}
          </dl>

          {result.output && result.status === "SUCCEEDED" && (
            <details className="result-output">
              <summary>Output Data</summary>
              <pre>{JSON.stringify(result.output, null, 2)}</pre>
            </details>
          )}

          <button onClick={fetchStatus} disabled={loading} className="refresh-btn">
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      )}

      {loading && !result && <div className="loading">Loading status...</div>}
    </div>
  );
}
