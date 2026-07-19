import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";

const client = generateClient<Schema>();

interface JobHistoryProps {
  onSelectExecution: (arn: string) => void;
}

/**
 * Job History tab.
 *
 * Shows past job executions for the current user (owner-based auth).
 * Clicking an execution navigates to the Results tab.
 */
export function JobHistory({ onSelectExecution }: JobHistoryProps) {
  const [jobs, setJobs] = useState<Schema["JobExecution"]["type"][]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchHistory() {
      try {
        const { data, errors } = await client.models.JobExecution.list({
          limit: 50,
        });
        if (errors) {
          setError(errors.map((e) => e.message).join(", "));
        } else {
          // Sort by startDate descending
          const sorted = [...(data || [])].sort((a, b) =>
            (b.startDate || "").localeCompare(a.startDate || "")
          );
          setJobs(sorted);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load history");
      } finally {
        setLoading(false);
      }
    }
    fetchHistory();
  }, []);

  const statusColor = (status: string | null | undefined) => {
    switch (status) {
      case "SUCCEEDED": return "status-succeeded";
      case "FAILED": return "status-failed";
      case "RUNNING": return "status-running";
      default: return "";
    }
  };

  if (loading) {
    return (
      <div className="job-history">
        <h2>History</h2>
        <p>Loading job history...</p>
      </div>
    );
  }

  return (
    <div className="job-history">
      <h2>History</h2>

      {error && <div className="error-message">{error}</div>}

      {jobs.length === 0 && !error && (
        <p className="empty-state">No job executions found. Start a processing job from the Process tab.</p>
      )}

      {jobs.length > 0 && (
        <table className="history-table">
          <thead>
            <tr>
              <th>Pattern</th>
              <th>Input Prefix</th>
              <th>Status</th>
              <th>Started</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id}>
                <td>{job.pattern.replace(/_/g, " ")}</td>
                <td className="prefix">{job.inputPrefix}</td>
                <td>
                  <span className={`status-badge ${statusColor(job.status)}`}>
                    {job.status || "UNKNOWN"}
                  </span>
                </td>
                <td>
                  {job.startDate
                    ? new Date(job.startDate).toLocaleString()
                    : "-"}
                </td>
                <td>
                  <button
                    className="view-btn"
                    onClick={() => onSelectExecution(job.executionArn)}
                  >
                    View
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
