import { useState, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";

const client = generateClient<Schema>();

/**
 * Athena SQL Query Panel.
 *
 * Allows users to run SQL queries against data cataloged in Glue
 * (including data on FSx for ONTAP via S3 AP + Glue Crawler).
 */
export function AthenaQueryPanel() {
  const [sql, setSql] = useState("SELECT * FROM default.my_table LIMIT 10");
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
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setLoading(false);
    }
  }, [sql, database]);

  return (
    <div className="athena-panel">
      <div className="athena-header">
        <h3>SQL Query (Athena)</h3>
        <input
          type="text"
          value={database}
          onChange={(e) => setDatabase(e.target.value)}
          placeholder="Database"
          className="athena-db-input"
          aria-label="Database name"
        />
      </div>
      <textarea
        className="athena-sql-input"
        value={sql}
        onChange={(e) => setSql(e.target.value)}
        rows={4}
        placeholder="SELECT * FROM ..."
        aria-label="SQL query"
      />
      <div className="athena-actions">
        <button onClick={runQuery} disabled={loading || !sql.trim()}>
          {loading ? "Running..." : "Run Query"}
        </button>
        {status && <span className="athena-status">{status}</span>}
      </div>

      {error && <div className="athena-error">{error}</div>}

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
          <div className="athena-row-count">{rows.length} rows returned</div>
        </div>
      )}
    </div>
  );
}
