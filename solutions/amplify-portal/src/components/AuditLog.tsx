import { useState } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

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
  /**
   * Which trail is being read.
   *
   * Two sources rather than one merged table, because they answer different questions and
   * neither substitutes. CloudTrail sees every object access and attributes it to the
   * access point's IAM role, which is the same principal for every portal user -- so it
   * establishes that a file was read without establishing who asked. The portal ledger
   * knows the Cognito user, and records actions that never reach S3 as a distinguishable
   * event, such as minting a presigned URL. Merging them would produce rows whose
   * "user" column meant something different from one line to the next.
   */
  const [source, setSource] = useState<"CLOUDTRAIL" | "PORTAL">("CLOUDTRAIL");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const { t } = useTranslation();

  const runQuery = async () => {
    setLoading(true);
    setError(null);
    setEvents([]);

    try {
      const response = await client.queries.queryAuditLog({
        fileKeyPrefix: fileFilter || undefined,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
        eventType: eventType,
        maxResults: 50,
        source,
      });

      if (response.data) {
        const rawEvents = response.data.events;
        // Handle events being string (JSON), array, or null
        let parsed: AuditEvent[] = [];
        if (Array.isArray(rawEvents)) {
          parsed = rawEvents as AuditEvent[];
        } else if (typeof rawEvents === "string") {
          try { parsed = JSON.parse(rawEvents); } catch { parsed = []; }
        }
        setEvents(parsed);
        if (response.data.error) {
          setError(response.data.error);
        }
      } else if (response.errors) {
        setError(response.errors.map((e: { message: string }) => e.message).join(", "));
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
      // CloudTrail: the S3 API call.
      case "GetObject": return "📖";
      case "PutObject": return "📝";
      case "DeleteObject": return "🗑️";
      case "ListBucket": return "📂";
      // Portal ledger: what the user asked the portal to do. Distinct names, because a
      // minted URL is not a read and an upload link is not a write -- not yet.
      case "DOWNLOAD": return "⬇️";
      case "SHARE_LINK": return "🔗";
      case "UPLOAD_LINK": return "⬆️";
      case "DELETE": return "🗑️";
      default: return "❓";
    }
  };

  return (
    <div className="audit-log">
      <h2>{t("auditTitle")}</h2>
      <p className="audit-description">{t("auditDescription")}</p>

      <div className="audit-source" role="radiogroup" aria-label={t("auditSourceLabel")}>
        {(["CLOUDTRAIL", "PORTAL"] as const).map((option) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={source === option}
            className={`audit-source-option ${source === option ? "active" : ""}`}
            onClick={() => {
              setSource(option);
              // Cleared rather than left in place: the columns mean different things per
              // source, so keeping the previous rows would relabel them.
              setEvents([]);
              setError(null);
            }}
          >
            {option === "CLOUDTRAIL" ? t("auditSourceCloudTrail") : t("auditSourcePortal")}
          </button>
        ))}
      </div>
      <p className="audit-source-description">
        {source === "CLOUDTRAIL" ? t("auditSourceCloudTrailDesc") : t("auditSourcePortalDesc")}
      </p>

      <div className="audit-filters">
        <div className="filter-row">
          <div className="filter-group">
            <label htmlFor="audit-file-filter">{t("auditFilterFileLabel")}</label>
            <input
              id="audit-file-filter"
              type="text"
              value={fileFilter}
              onChange={(e) => setFileFilter(e.target.value)}
              placeholder={t("auditFilterFilePlaceholder")}
            />
          </div>
          <div className="filter-group">
            <label htmlFor="audit-event-type">{t("auditFilterEventTypeLabel")}</label>
            <select
              id="audit-event-type"
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
            >
              <option value="ALL">{t("auditFilterEventTypeAll")}</option>
              {source === "CLOUDTRAIL" ? (
                <>
                  <option value="READ">{t("auditFilterEventTypeRead")}</option>
                  <option value="WRITE">{t("auditFilterEventTypeWrite")}</option>
                </>
              ) : (
                <>
                  {/* The ledger's own action names. Offering READ/WRITE here would
                      match nothing, which reads as "no activity". */}
                  <option value="DOWNLOAD">{t("auditActionDownload")}</option>
                  <option value="SHARE_LINK">{t("auditActionShareLink")}</option>
                  <option value="UPLOAD_LINK">{t("auditActionUploadLink")}</option>
                  <option value="DELETE">{t("auditActionDelete")}</option>
                </>
              )}
            </select>
          </div>
        </div>
        <div className="filter-row">
          <div className="filter-group">
            <label htmlFor="audit-start-date">{t("auditFilterFromLabel")}</label>
            <input
              id="audit-start-date"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>
          <div className="filter-group">
            <label htmlFor="audit-end-date">{t("auditFilterToLabel")}</label>
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
            {loading ? t("auditSearchingBtn") : t("auditSearchBtn")}
          </button>
        </div>
      </div>

      {error && (
        <div className="protection-info" style={{ marginTop: "1rem" }}>
          <h3>{t("auditConfigRequired")}</h3>
          <p>{t("auditConfigRequiredDesc")}</p>
          <ul>
            <li>{t("auditConfigStep1")}</li>
            <li>{t("auditConfigStep2")}</li>
            <li>{t("auditConfigStep3")}</li>
          </ul>
          <details>
            <summary>{t("errorDetails")}</summary>
            <pre style={{ fontSize: "0.8rem", overflow: "auto", padding: "0.5rem", background: "var(--color-surface-subtle)", borderRadius: "4px" }}>{error}</pre>
          </details>
        </div>
      )}

      {events.length > 0 && (
        <div className="audit-results">
          <table className="audit-table" role="grid" aria-label={t("auditTitle")}>
            <thead>
              <tr>
                <th scope="col">{t("auditColTime")}</th>
                <th scope="col">{t("auditColAction")}</th>
                <th scope="col">{t("auditColUser")}</th>
                <th scope="col">{t("auditColFile")}</th>
                <th scope="col">{t("auditColSourceIp")}</th>
                <th scope="col">{t("auditColStatus")}</th>
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
            {events.length} {t("auditEventsFound")}
          </div>
        </div>
      )}

      {!loading && events.length === 0 && !error && (
        <p className="empty-state">{t("auditEmptyState")}</p>
      )}
    </div>
  );
}
