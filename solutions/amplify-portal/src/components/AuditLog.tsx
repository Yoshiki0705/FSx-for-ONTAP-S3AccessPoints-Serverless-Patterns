import { useState } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";

const client = generateClient<Schema>();

interface AuditEvent {
  timestamp: string;
  action: string;
  userArn: string;
  principalId: string;
  sourceIp: string;
  fileKey: string;
  bucketName: string;
  errorCode: string;
  errorMessage: string;
}

/**
 * Audit Log component for the compliance "Audit" tab.
 *
 * Queries CloudTrail S3 data events via Athena to show:
 * - Who accessed which file
 * - When the access occurred
 * - What action was performed (GetObject, PutObject, DeleteObject)
 * - Whether the access succeeded or was denied
 *
 * Architecture:
 *   AppSync query → Lambda → Athena SQL → CloudTrail S3 data event logs
 *
 * Pre-requisites:
 *   - CloudTrail trail with S3 data events for the S3 AP ARN
 *   - Athena table over CloudTrail logs (Glue Crawler or manual CREATE TABLE)
 *   - ATHENA_AUDIT_DATABASE, ATHENA_AUDIT_TABLE, ATHENA_AUDIT_OUTPUT env vars
 */
export function AuditLog() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileFilter, setFileFilter] = useState("");
  const [eventType, setEventType] = useState("ALL");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const runQuery = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await client.queries.queryAuditLog({
        fileKeyPrefix: fileFilter || undefined,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
        eventType: eventType,
        maxResults: 50,
      });

      if (response.data) {
        setEvents((response.data.events || []) as AuditEvent[]);
        if (response.data.error) {
          setError(response.data.error);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to query audit log");
    } finally {
      setLoading(false);
    }
  };

  const formatUser = (userArn: string): string => {
    if (!userArn) return "—";
    // Extract the last part of the ARN (role/user name)
    const parts = userArn.split("/");
    return parts[parts.length - 1] || userArn;
  };

  const formatDate = (iso: string): string => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  const getActionIcon = (action: string): string => {
    switch (action) {
      case "GetObject": return "📖";
      case "PutObject": return "📝";
      case "DeleteObject": return "🗑️";
      case "ListBucket": return "📂";
      default: return "❓";
    }
  };

  return (
    <div className="audit-log">
      <h2>Audit Trail</h2>
      <p className="audit-description">
        File access events from CloudTrail S3 data events.
        Shows who accessed which file, when, and what action was performed.
      </p>

      <div className="audit-filters">
        <div className="filter-row">
          <div className="filter-group">
            <label htmlFor="audit-file-filter">File path contains</label>
            <input
              id="audit-file-filter"
              type="text"
              value={fileFilter}
              onChange={(e) => setFileFilter(e.target.value)}
              placeholder="e.g., contracts/ or report.pdf"
            />
          </div>
          <div className="filter-group">
            <label htmlFor="audit-event-type">Event type</label>
            <select
              id="audit-event-type"
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
            >
              <option value="ALL">All</option>
              <option value="READ">Read (Get/List)</option>
              <option value="WRITE">Write (Put/Delete)</option>
            </select>
          </div>
        </div>
        <div className="filter-row">
          <div className="filter-group">
            <label htmlFor="audit-start-date">From</label>
            <input
              id="audit-start-date"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>
          <div className="filter-group">
            <label htmlFor="audit-end-date">To</label>
            <input
              id="audit-end-date"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
          <button
            onClick={runQuery}
            disabled={loading}
            className="audit-query-btn"
          >
            {loading ? "Querying..." : "Search"}
          </button>
        </div>
      </div>

      {error && (
        <div className="protection-info" style={{ marginTop: "1rem" }}>
          <h3>⚠️ Audit Query Configuration Required</h3>
          <p>
            The Audit Trail queries CloudTrail S3 data events via Athena. If you see this message,
            the Athena query infrastructure is not yet configured.
          </p>
          <ul>
            <li>Enable CloudTrail S3 data events for your S3 AP ARN</li>
            <li>Create an Athena table over CloudTrail logs (Glue Crawler or manual DDL)</li>
            <li>Set <code>ATHENA_AUDIT_DATABASE</code>, <code>ATHENA_AUDIT_TABLE</code>, <code>ATHENA_AUDIT_OUTPUT</code> on the Lambda</li>
          </ul>
          <details>
            <summary>Error details</summary>
            <pre style={{ fontSize: "0.8rem", overflow: "auto", padding: "0.5rem", background: "#f5f5f5", borderRadius: "4px" }}>{error}</pre>
          </details>
        </div>
      )}

      {events.length > 0 && (
        <div className="audit-results">
          <table className="audit-table" role="grid" aria-label="File access audit trail">
            <thead>
              <tr>
                <th scope="col">Time</th>
                <th scope="col">Action</th>
                <th scope="col">User</th>
                <th scope="col">File</th>
                <th scope="col">Source IP</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {events.map((evt, idx) => (
                <tr key={idx} className={evt.errorCode ? "audit-row-error" : ""}>
                  <td className="audit-time">{formatDate(evt.timestamp)}</td>
                  <td>
                    <span title={evt.action}>
                      {getActionIcon(evt.action)} {evt.action}
                    </span>
                  </td>
                  <td className="audit-user" title={evt.userArn}>
                    {formatUser(evt.userArn)}
                  </td>
                  <td className="audit-file" title={evt.fileKey}>
                    {evt.fileKey || "—"}
                  </td>
                  <td className="audit-ip">{evt.sourceIp || "—"}</td>
                  <td>
                    {evt.errorCode ? (
                      <span className="audit-denied" title={evt.errorMessage}>
                        ❌ {evt.errorCode}
                      </span>
                    ) : (
                      <span className="audit-success">✅</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="audit-count">
            {events.length} event{events.length !== 1 ? "s" : ""} found
          </div>
        </div>
      )}

      {!loading && events.length === 0 && !error && (
        <p className="empty-state">
          Click "Search" to query the audit trail. Configure date range
          and file path filters to narrow results.
        </p>
      )}
    </div>
  );
}
