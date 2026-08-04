import { useState, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

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
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setLoading(false);
    }
  }, [sql, database]);

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
          <span style={{ fontSize: "0.75rem", color: "var(--text-secondary, #666)", whiteSpace: "nowrap" }}>
            ← Glue DB 名
          </span>
        </div>
      </div>
      <p style={{ margin: "0 0 0.75rem", fontSize: "0.8rem", color: "var(--text-secondary, #666)" }}>
        📦 <strong>データベース名</strong>: Glue Data Catalog 上のデータベース名を入力します。Glue Crawler でカタログ化したテーブルが格納されているデータベースです。未作成の場合は <code>default</code> のまま、<code>SHOW DATABASES</code> で確認できます。
      </p>

      <div className="athena-guidance" style={{ marginBottom: "1rem", padding: "0.75rem", background: "var(--surface-secondary, #f8f9fa)", borderRadius: "6px", fontSize: "0.85rem" }}>
        <p style={{ margin: "0 0 0.5rem" }}>
          <strong>💡 {t("athenaGuidanceTitle") || "使い方"}</strong>: FSx for ONTAP 上のファイルを Glue Crawler でカタログ化すると、ここから SQL で分析できます。
        </p>
        <details>
          <summary style={{ cursor: "pointer", color: "var(--accent-color, #0066cc)" }}>
            📝 クエリ例を見る
          </summary>
          <div style={{ marginTop: "0.5rem" }}>
            <p style={{ margin: "0.25rem 0", fontFamily: "monospace", fontSize: "0.8rem" }}>
              -- ファイル一覧（サイズ降順 Top 20）<br/>
              <code>SELECT key, size, last_modified FROM default.s3_objects ORDER BY size DESC LIMIT 20</code>
            </p>
            <p style={{ margin: "0.25rem 0", fontFamily: "monospace", fontSize: "0.8rem" }}>
              -- 特定フォルダの合計サイズ<br/>
              <code>SELECT SUM(size) as total_bytes FROM default.s3_objects WHERE key LIKE 'engineering/%'</code>
            </p>
            <p style={{ margin: "0.25rem 0", fontFamily: "monospace", fontSize: "0.8rem" }}>
              -- 最近 7 日間に更新されたファイル<br/>
              <code>SELECT key, last_modified FROM default.s3_objects WHERE last_modified &gt; current_date - interval '7' day</code>
            </p>
            <p style={{ margin: "0.5rem 0 0", fontSize: "0.8rem", color: "var(--text-secondary, #666)" }}>
              ※ テーブル名は Glue Crawler の設定に依存します。<code>SHOW TABLES IN default</code> で確認できます。
            </p>
          </div>
        </details>
      </div>

      <textarea
        className="athena-sql-input"
        value={sql}
        onChange={(e) => setSql(e.target.value)}
        rows={4}
        placeholder={"-- 例: SHOW TABLES IN default\n-- 例: SELECT key, size FROM default.s3_objects LIMIT 20\nSELECT * FROM default.my_table LIMIT 10"}
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
             style={status === "SETUP_REQUIRED" ? { background: "#fff3cd", borderColor: "#ffc107", color: "#856404", padding: "1rem", borderRadius: "6px", border: "1px solid" } : undefined}>
          {status === "SETUP_REQUIRED" && <strong>⚙️ セットアップが必要です</strong>}
          {status === "SETUP_REQUIRED" && <br/>}
          {error}
          {status === "SETUP_REQUIRED" && (
            <details style={{ marginTop: "0.5rem" }}>
              <summary style={{ cursor: "pointer" }}>📖 設定手順を見る</summary>
              <ol style={{ marginTop: "0.5rem", paddingLeft: "1.5rem", fontSize: "0.85rem" }}>
                <li>AWS コンソール → Athena → ワークグループ → 「primary」を選択</li>
                <li>「設定を編集」→「クエリ結果の場所」に S3 パスを入力（例: <code>s3://your-bucket/athena-results/</code>）</li>
                <li>保存して、このパネルでクエリを再実行</li>
              </ol>
              <p style={{ fontSize: "0.8rem", color: "#666" }}>
                または <code>portal-config.ts</code> の環境変数 <code>ATHENA_OUTPUT_LOCATION</code> に S3 パスを設定してリデプロイしてください。
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
          <div className="athena-row-count">{rows.length} rows returned</div>
        </div>
      )}
    </div>
  );
}
