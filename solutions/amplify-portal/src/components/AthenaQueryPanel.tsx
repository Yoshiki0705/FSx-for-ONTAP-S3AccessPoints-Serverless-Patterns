import { useState, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";
import { withNodes } from "../utils/richText";
import { CatalogBrowser } from "./CatalogBrowser";

const client = generateClient<Schema>();

/**
 * Athena SQL Query Panel.
 *
 * Allows users to run SQL queries against data cataloged in Glue
 * (including data on FSx for ONTAP via S3 AP + Glue Crawler).
 */
export function AthenaQueryPanel() {
  const { t } = useTranslation();
  const [sql, setSql] = useState("SHOW TABLES IN default");
  const [database, setDatabase] = useState("default");
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<string[][]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const runQuery = useCallback(async () => {
    if (!sql.trim()) return;
    setLoading(true);
    setError(null);
    setColumns([]);
    setRows([]);

    try {
      const response = await client.mutations.runAthenaQuery({ sql, database });
      if (response.data) {
        setStatus(response.data.status || null);
        if (response.data.error) {
          setError(response.data.error);
        } else {
          setColumns(response.data.columns as string[] || []);
          setRows(response.data.rows as string[][] || []);
        }
      }
    } catch (err) {
      // A thrown non-Error carries no message worth showing, so fall back to a
      // translated one rather than rendering "[object Object]".
      setError(err instanceof Error ? err.message : t("aqQueryFailed"));
    } finally {
      setLoading(false);
    }
  }, [sql, database, t]);

  return (
    <div className="athena-panel">
      <div className="athena-header">
        <h3>{t("athenaTitle")}</h3>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <input
            type="text"
            value={database}
            onChange={(e) => setDatabase(e.target.value)}
            placeholder={t("aqDatabase")}
            className="athena-db-input"
            aria-label={t("aqDatabaseAria")}
            title={t("aqDatabaseHint")}
          />
          <span style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)", whiteSpace: "nowrap" }}>
            {t("aqDatabaseArrow")}
          </span>
        </div>
      </div>
      <p style={{ margin: "0 0 0.75rem", fontSize: "0.8rem", color: "var(--color-text-secondary)" }}>
        📦 <strong>{t("aqDatabaseAria")}</strong>:{" "}
        {withNodes(t("aqDatabaseExplain"), {
          db: <code>default</code>,
          cmd: <code>SHOW DATABASES</code>,
        })}
      </p>

      {/* Browsing the catalog beats guessing a database name and retrying. */}
      <CatalogBrowser
        onSelectTable={(db, table) => {
          setDatabase(db);
          setSql(`SELECT * FROM ${db}.${table} LIMIT 20`);
        }}
      />

      <div className="athena-guidance" style={{ marginBottom: "1rem", padding: "0.75rem", background: "var(--color-surface-subtle)", borderRadius: "6px", fontSize: "0.85rem" }}>
        <p style={{ margin: "0 0 0.5rem" }}>
          <strong>💡 {t("athenaGuidanceTitle")}</strong>: {t("aqGuidanceBody")}
        </p>
        <details>
          <summary style={{ cursor: "pointer", color: "var(--color-primary-text)" }}>
            📝 {t("aqExamplesToggle")}
          </summary>
          <div style={{ marginTop: "0.5rem" }}>
            <p style={{ margin: "0.25rem 0", fontFamily: "monospace", fontSize: "0.8rem" }}>
              {/* The SQL stays as written; only the comment describing it is translated. */}
              -- {t("aqExampleTopSizes")}<br/>
              <code>SELECT key, size, last_modified FROM default.s3_objects ORDER BY size DESC LIMIT 20</code>
            </p>
            <p style={{ margin: "0.25rem 0", fontFamily: "monospace", fontSize: "0.8rem" }}>
              -- {t("aqExampleFolderTotal")}<br/>
              <code>SELECT SUM(size) as total_bytes FROM default.s3_objects WHERE key LIKE 'engineering/%'</code>
            </p>
            <p style={{ margin: "0.25rem 0", fontFamily: "monospace", fontSize: "0.8rem" }}>
              -- {t("aqExampleRecent")}<br/>
              <code>SELECT key, last_modified FROM default.s3_objects WHERE last_modified &gt; current_date - interval '7' day</code>
            </p>
            <p style={{ margin: "0.5rem 0 0", fontSize: "0.8rem", color: "var(--color-text-secondary)" }}>
              ※ {withNodes(t("aqExamplesNote"), { cmd: <code>SHOW TABLES IN default</code> })}
            </p>
          </div>
        </details>
      </div>

      <textarea
        className="athena-sql-input"
        value={sql}
        onChange={(e) => setSql(e.target.value)}
        rows={4}
        placeholder={t("aqSqlPlaceholder")}
        aria-label={t("aqSqlAria")}
      />
      <div className="athena-actions">
        <button onClick={runQuery} disabled={loading || !sql.trim()}>
          {loading ? t("athenaRunning") : t("athenaRun")}
        </button>
        {status && <span className="athena-status">{status}</span>}
      </div>

      {error && (
        <div className={`athena-error ${status === "SETUP_REQUIRED" ? "athena-setup-hint" : ""}`}
             style={status === "SETUP_REQUIRED" ? { background: "var(--color-warning-bg)", borderColor: "var(--color-warning)", color: "var(--color-warning-text)", padding: "1rem", borderRadius: "6px", border: "1px solid" } : undefined}>
          {status === "SETUP_REQUIRED" && <strong>⚙️ {t("aqSetupRequired")}</strong>}
          {status === "SETUP_REQUIRED" && <br/>}
          {error}
          {status === "SETUP_REQUIRED" && (
            <details style={{ marginTop: "0.5rem" }}>
              <summary style={{ cursor: "pointer" }}>📖 {t("aqSetupToggle")}</summary>
              <ol style={{ marginTop: "0.5rem", paddingLeft: "1.5rem", fontSize: "0.85rem" }}>
                <li>{t("aqSetupStep1")}</li>
                <li>
                  {withNodes(t("aqSetupStep2"), {
                    path: <code>s3://your-bucket/athena-results/</code>,
                  })}
                </li>
                <li>{t("aqSetupStep3")}</li>
              </ol>
              <p style={{ fontSize: "0.8rem", color: "var(--color-text-secondary)" }}>
                {withNodes(t("aqSetupEnvHint"), {
                  file: <code>portal-config.ts</code>,
                  env: <code>ATHENA_OUTPUT_LOCATION</code>,
                })}
              </p>
            </details>
          )}
        </div>
      )}

      {columns.length > 0 && (
        <div className="athena-results">
          <table>
            <thead>
              <tr>
                {columns.map((col, i) => (
                  <th key={i}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j}>{cell}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="athena-row-count">
            {t("aqRowsReturned").replace("{count}", String(rows.length))}
          </div>
        </div>
      )}
    </div>
  );
}
