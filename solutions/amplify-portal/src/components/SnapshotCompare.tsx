import { useState, useEffect, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";

const client = generateClient<Schema>();

interface FileItem {
  key: string;
  size: number | null;
  lastModified: string | null;
  storageClass: string | null;
}

interface CompareResult {
  key: string;
  currentSize: number | null;
  cloneSize: number | null;
  currentModified: string | null;
  cloneModified: string | null;
  status: "unchanged" | "modified" | "added" | "deleted";
}

interface SnapshotCompareProps {
  /** S3 AP alias for the FlexClone volume (passed from RestoreFromSnapshot result) */
  cloneApAlias: string;
  /** Human-readable clone label (e.g., snapshot name) */
  cloneLabel?: string;
}

/**
 * Snapshot Compare (Side-by-side diff) component.
 *
 * Displays files from two S3 Access Points side by side:
 * - Left: Current volume (default S3 AP)
 * - Right: FlexClone volume (clone S3 AP)
 *
 * Highlights differences:
 * - Added (green): File exists in current but not in clone
 * - Deleted (red): File exists in clone but not in current
 * - Modified (yellow): File exists in both but size differs
 * - Unchanged (gray): Identical in both
 *
 * Architecture:
 *   Two parallel listFiles queries (current AP + clone AP) → client-side diff
 *
 * Note: Requires a FlexClone volume with its own S3 AP already created
 * (via RestoreFromSnapshot or FlexClone workflow).
 */
export function SnapshotCompare({ cloneApAlias, cloneLabel }: SnapshotCompareProps) {
  const [compareResults, setCompareResults] = useState<CompareResult[]>([]);
  const [currentPrefix, setCurrentPrefix] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadComparison = useCallback(async (prefix: string) => {
    setLoading(true);
    setError(null);

    try {
      // Fetch both file lists in parallel
      const [currentResp, cloneResp] = await Promise.all([
        client.queries.listFiles({ prefix, maxKeys: 500 }),
        client.queries.listFilesFromAp({
          prefix,
          maxKeys: 500,
          apAlias: cloneApAlias,
        }),
      ]);

      const currFiles = (currentResp.data?.files || []) as FileItem[];
      const clnFiles = (cloneResp.data?.files || []) as FileItem[];

      // Compute diff
      const currMap = new Map(currFiles.map((f) => [f.key, f]));
      const clnMap = new Map(clnFiles.map((f) => [f.key, f]));
      const allKeys = new Set([...currMap.keys(), ...clnMap.keys()]);

      const results: CompareResult[] = [];
      for (const key of allKeys) {
        const curr = currMap.get(key);
        const cln = clnMap.get(key);

        if (curr && cln) {
          const sizeChanged = curr.size !== cln.size;
          results.push({
            key,
            currentSize: curr.size,
            cloneSize: cln.size,
            currentModified: curr.lastModified,
            cloneModified: cln.lastModified,
            status: sizeChanged ? "modified" : "unchanged",
          });
        } else if (curr && !cln) {
          results.push({
            key,
            currentSize: curr.size,
            cloneSize: null,
            currentModified: curr.lastModified,
            cloneModified: null,
            status: "added",
          });
        } else if (!curr && cln) {
          results.push({
            key,
            currentSize: null,
            cloneSize: cln.size,
            currentModified: null,
            cloneModified: cln.lastModified,
            status: "deleted",
          });
        }
      }

      // Sort: modified/added/deleted first, then unchanged
      results.sort((a, b) => {
        const order = { modified: 0, added: 1, deleted: 2, unchanged: 3 };
        return order[a.status] - order[b.status];
      });

      setCompareResults(results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load comparison");
    } finally {
      setLoading(false);
    }
  }, [cloneApAlias]);

  useEffect(() => {
    if (cloneApAlias) {
      loadComparison(currentPrefix);
    }
  }, [currentPrefix, cloneApAlias, loadComparison]);

  const formatSize = (bytes: number | null) => {
    if (bytes === null) return "—";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (iso: string | null) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleDateString();
    } catch {
      return iso;
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "modified": return "✏️";
      case "added": return "➕";
      case "deleted": return "🗑️";
      case "unchanged": return "⚪";
      default: return "❓";
    }
  };

  const stats = {
    total: compareResults.length,
    modified: compareResults.filter((r) => r.status === "modified").length,
    added: compareResults.filter((r) => r.status === "added").length,
    deleted: compareResults.filter((r) => r.status === "deleted").length,
    unchanged: compareResults.filter((r) => r.status === "unchanged").length,
  };

  if (!cloneApAlias) {
    return (
      <div className="snapshot-compare empty-state">
        <p>Select a snapshot and create a FlexClone to compare file versions.</p>
      </div>
    );
  }

  return (
    <div className="snapshot-compare">
      <div className="compare-header">
        <h3>Side-by-side Compare</h3>
        <div className="compare-labels">
          <span className="compare-label current">Current Volume</span>
          <span className="compare-vs">vs</span>
          <span className="compare-label clone">
            {cloneLabel || "FlexClone"} ({cloneApAlias.slice(0, 20)}...)
          </span>
        </div>
      </div>

      {/* Breadcrumb */}
      <div className="compare-breadcrumb">
        <button onClick={() => setCurrentPrefix("")}>/</button>
        {currentPrefix.split("/").filter(Boolean).map((part, idx, arr) => (
          <span key={idx}>
            {" / "}
            <button onClick={() => setCurrentPrefix(arr.slice(0, idx + 1).join("/") + "/")}>
              {part}
            </button>
          </span>
        ))}
      </div>

      {/* Summary stats */}
      {!loading && compareResults.length > 0 && (
        <div className="compare-stats">
          <span className="stat-total">{stats.total} files</span>
          {stats.modified > 0 && <span className="stat-modified">✏️ {stats.modified} modified</span>}
          {stats.added > 0 && <span className="stat-added">➕ {stats.added} added</span>}
          {stats.deleted > 0 && <span className="stat-deleted">🗑️ {stats.deleted} deleted</span>}
          <span className="stat-unchanged">⚪ {stats.unchanged} unchanged</span>
        </div>
      )}

      {loading && <div className="loading">Comparing files...</div>}
      {error && <div className="error-message">{error}</div>}

      {!loading && compareResults.length > 0 && (
        <table className="compare-table" role="grid" aria-label="File comparison">
          <thead>
            <tr>
              <th scope="col">Status</th>
              <th scope="col">File</th>
              <th scope="col">Current Size</th>
              <th scope="col">Clone Size</th>
              <th scope="col">Current Date</th>
              <th scope="col">Clone Date</th>
            </tr>
          </thead>
          <tbody>
            {compareResults.map((row) => (
              <tr
                key={row.key}
                className={`compare-row compare-${row.status}`}
                onClick={() => {
                  if (row.key.endsWith("/")) setCurrentPrefix(row.key);
                }}
                style={row.key.endsWith("/") ? { cursor: "pointer" } : undefined}
              >
                <td className="compare-status">{getStatusIcon(row.status)}</td>
                <td className="compare-file" title={row.key}>
                  {row.key.replace(currentPrefix, "")}
                </td>
                <td>{formatSize(row.currentSize)}</td>
                <td>{formatSize(row.cloneSize)}</td>
                <td className="compare-date">{formatDate(row.currentModified)}</td>
                <td className="compare-date">{formatDate(row.cloneModified)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!loading && compareResults.length === 0 && !error && (
        <p className="empty-state">No files found in this path.</p>
      )}
    </div>
  );
}
