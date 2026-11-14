import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";
import { patternLabel } from "../lib/industryUseCases";

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
  const { t } = useTranslation();
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
          void settleRunning(sorted);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load history");
      } finally {
        setLoading(false);
      }
    }
    // A row is written as RUNNING when the job starts and nothing else updates it, so
    // without this every job stayed RUNNING in the history for good. Ask Step Functions
    // once for the rows that still say RUNNING and store the final state.
    async function settleRunning(rows: Schema["JobExecution"]["type"][]) {
      const running = rows.filter((row) => row.status === "RUNNING");
      const updates = await Promise.all(
        running.map(async (row) => {
          try {
            const { data } = await client.queries.getJobStatus({ executionArn: row.executionArn });
            if (!data?.status || data.status === "RUNNING") return null;
            await client.models.JobExecution.update({
              id: row.id,
              status: data.status,
              stopDate: data.stopDate ?? undefined,
            });
            return { id: row.id, status: data.status };
          } catch {
            return null; // Leave the row as it is; the next visit tries again.
          }
        })
      );
      const done = new Map(updates.filter((u) => u !== null).map((u) => [u!.id, u!.status]));
      if (done.size > 0) {
        setJobs((prev) => prev.map((row) => (done.has(row.id) ? { ...row, status: done.get(row.id)! } : row)));
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
        <h2>{t("labelHistory")}</h2>
        <p>{t("jhLoading")}</p>
      </div>
    );
  }

  return (
    <div className="job-history">
      <h2>{t("labelHistory")}</h2>

      {error && <div className="error-message">{error}</div>}

      {jobs.length === 0 && !error && (
        <p className="empty-state">{t("jobHistoryEmpty")}</p>
      )}

      {jobs.length > 0 && (
        <table className="history-table">
          <thead>
            <tr>
              <th>{t("jobHistoryPattern")}</th>
              <th>{t("jhInputPrefix")}</th>
              <th>{t("rmState")}</th>
              <th>{t("labelStarted")}</th>
              <th>{t("rmActions")}</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id}>
                <td>{patternLabel(job.pattern, t)}</td>
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
                    {t("jhView")}
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
