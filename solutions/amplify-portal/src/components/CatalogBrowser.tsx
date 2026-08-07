import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

interface Database {
  name: string;
  description: string;
}

interface Table {
  name: string;
  description: string;
  columns: number;
  location: string;
}

interface Column {
  name: string;
  type: string;
  comment?: string;
}

interface SchemaResult {
  schema: Column[];
  partitionKeys: { name: string; type: string }[];
  location: string;
}

/** Unwrap the JSON payload the Glue resolver returns. */
function parsed<T>(data: unknown): T | null {
  if (!data) return null;
  try {
    return typeof data === "string" ? (JSON.parse(data) as T) : (data as T);
  } catch {
    return null;
  }
}

async function browse<T>(args: { action: string; database?: string; table?: string }) {
  const response = await client.queries.browseCatalog(args);
  return parsed<T & { error?: string | null }>(response.data);
}

interface CatalogBrowserProps {
  /** Fill the query editor with this table, so browsing leads to a query. */
  onSelectTable: (database: string, table: string) => void;
}

/**
 * Glue Data Catalog browser.
 *
 * The query panel used to ask for a database name in a text box and suggest
 * running `SHOW DATABASES` to find one. The catalog was already readable
 * through `browseCatalog`, so this shows the databases, their tables and each
 * table's columns instead of asking the user to guess and retry.
 *
 * Loaded on demand rather than on mount: a portal deployed without a crawler
 * has an empty catalog, and three Glue calls on every visit to the analytics
 * tab would be three calls for nothing.
 */
export function CatalogBrowser({ onSelectTable }: CatalogBrowserProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [selectedDb, setSelectedDb] = useState<string | null>(null);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);

  const databases = useQuery({
    queryKey: ["catalog", "databases"],
    enabled: open,
    queryFn: async () => {
      const data = await browse<{ databases: Database[] }>({ action: "listDatabases" });
      if (data?.error) throw new Error(data.error);
      return data?.databases ?? [];
    },
  });

  const tables = useQuery({
    queryKey: ["catalog", "tables", selectedDb],
    enabled: open && !!selectedDb,
    queryFn: async () => {
      const data = await browse<{ tables: Table[] }>({
        action: "listTables",
        database: selectedDb!,
      });
      if (data?.error) throw new Error(data.error);
      return data?.tables ?? [];
    },
  });

  const schema = useQuery({
    queryKey: ["catalog", "schema", selectedDb, selectedTable],
    enabled: open && !!selectedDb && !!selectedTable,
    queryFn: async () => {
      const data = await browse<SchemaResult>({
        action: "getSchema",
        database: selectedDb!,
        table: selectedTable!,
      });
      if (data?.error) throw new Error(data.error);
      return data ?? null;
    },
  });

  const message = (error: unknown) => (error instanceof Error ? error.message : String(error));

  return (
    <div className="catalog-browser">
      <button
        className="catalog-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        🗂️ {open ? t("catalogHide") : t("catalogShow")}
      </button>

      {open && (
        <div className="catalog-panel">
          <p className="rm-hint">{t("catalogHint")}</p>

          <div className="catalog-columns">
            <div className="catalog-column">
              <h5>{t("catalogDatabases")}</h5>
              {databases.isPending ? (
                <p className="rm-loading-sm">…</p>
              ) : databases.error ? (
                <div className="error-message">{message(databases.error)}</div>
              ) : databases.data?.length === 0 ? (
                // An empty catalog is the normal state before a crawler runs, so it
                // is explained rather than shown as a blank column.
                <p className="rm-empty-sm">{t("catalogNoDatabases")}</p>
              ) : (
                <ul className="catalog-list">
                  {databases.data?.map((db) => (
                    <li key={db.name}>
                      <button
                        className={selectedDb === db.name ? "active" : ""}
                        onClick={() => {
                          setSelectedDb(db.name);
                          setSelectedTable(null);
                        }}
                        title={db.description || db.name}
                      >
                        {db.name}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="catalog-column">
              <h5>{t("catalogTables")}</h5>
              {!selectedDb ? (
                <p className="rm-empty-sm">{t("catalogPickDatabase")}</p>
              ) : tables.isPending ? (
                <p className="rm-loading-sm">…</p>
              ) : tables.error ? (
                <div className="error-message">{message(tables.error)}</div>
              ) : tables.data?.length === 0 ? (
                <p className="rm-empty-sm">{t("catalogNoTables")}</p>
              ) : (
                <ul className="catalog-list">
                  {tables.data?.map((tb) => (
                    <li key={tb.name}>
                      <button
                        className={selectedTable === tb.name ? "active" : ""}
                        onClick={() => setSelectedTable(tb.name)}
                        title={tb.location || tb.name}
                      >
                        {tb.name}
                        <span className="catalog-count">{tb.columns}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="catalog-column catalog-schema">
              <h5>{t("catalogSchema")}</h5>
              {!selectedTable ? (
                <p className="rm-empty-sm">{t("catalogPickTable")}</p>
              ) : schema.isPending ? (
                <p className="rm-loading-sm">…</p>
              ) : schema.error ? (
                <div className="error-message">{message(schema.error)}</div>
              ) : (
                <>
                  <table className="rm-table catalog-schema-table">
                    <thead>
                      <tr>
                        <th>{t("catalogColumn")}</th>
                        <th>{t("catalogType")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {schema.data?.schema.map((col) => (
                        <tr key={col.name}>
                          <td>{col.name}</td>
                          <td><code>{col.type}</code></td>
                        </tr>
                      ))}
                      {/* Partition keys are separate in Glue and matter when writing a
                          WHERE clause that avoids a full scan, so they are labelled. */}
                      {schema.data?.partitionKeys.map((key) => (
                        <tr key={`p-${key.name}`} className="catalog-partition">
                          <td>{key.name}</td>
                          <td>
                            <code>{key.type}</code>{" "}
                            <span className="catalog-partition-tag">{t("catalogPartition")}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {schema.data?.location && (
                    <p className="rm-hint catalog-location">
                      {t("catalogLocation")}: <code>{schema.data.location}</code>
                    </p>
                  )}
                  <button
                    className="rm-btn-primary"
                    onClick={() => onSelectTable(selectedDb!, selectedTable)}
                  >
                    {t("catalogUseInQuery")}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
