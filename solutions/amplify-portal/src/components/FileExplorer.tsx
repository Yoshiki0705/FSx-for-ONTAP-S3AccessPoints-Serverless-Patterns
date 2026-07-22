import { useState, useEffect, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { portalSettings } from "../portal-settings";
import { FilePreview } from "./FilePreview";
import { RestoreFromSnapshot } from "./RestoreFromSnapshot";
import { ShareLink } from "./ShareLink";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

interface FileExplorerProps {
  onSelectPrefix: (prefix: string) => void;
  onFileSelect?: (fileKey: string, fileName: string) => void;
}

interface FileItem {
  key: string;
  size: number | null;
  lastModified: string | null;
  storageClass: string | null;
}

/**
 * File Explorer component.
 *
 * Displays files from FSx for ONTAP volume via S3 Access Point.
 * Supports:
 * - Directory navigation (prefix-based)
 * - Pagination (1000 objects per page)
 * - File selection for processing
 */
export function FileExplorer({ onSelectPrefix, onFileSelect }: FileExplorerProps) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [currentPrefix, setCurrentPrefix] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [continuationToken, setContinuationToken] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const { t } = useTranslation();

  const loadFiles = useCallback(async (prefix: string, token?: string | null) => {
    setLoading(true);
    setError(null);

    try {
      const response = await client.queries.listFiles({
        prefix,
        maxKeys: 100,
        continuationToken: token || undefined,
      });

      if (response.data) {
        const newFiles = (response.data.files || []) as FileItem[];
        setFiles(token ? (prev) => [...prev, ...newFiles] : newFiles);
        setContinuationToken(response.data.nextContinuationToken || null);
        setHasMore(response.data.isTruncated || false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load files");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFiles(currentPrefix);
  }, [currentPrefix, loadFiles]);

  const navigateToFolder = (folderKey: string) => {
    setCurrentPrefix(folderKey);
    setContinuationToken(null);
    setFiles([]);
  };

  const navigateUp = () => {
    const parts = currentPrefix.split("/").filter(Boolean);
    parts.pop();
    const parentPrefix = parts.length > 0 ? parts.join("/") + "/" : "";
    navigateToFolder(parentPrefix);
  };

  // Separate folders (common prefixes) from files
  const folders = files
    .filter((f) => f.storageClass === "DIRECTORY" || f.key.endsWith("/"))
    .map((f) => f.key);
  const regularFiles = files.filter(
    (f) => f.storageClass !== "DIRECTORY" && !f.key.endsWith("/")
  );

  const formatSize = (bytes: number | null) => {
    if (bytes === null) return "-";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  return (
    <div className="file-explorer">
      <div className="file-explorer-header">
        <h2>{t("filesTitle")}</h2>
        <div className="breadcrumb">
          <button onClick={() => navigateToFolder("")}>/</button>
          {currentPrefix.split("/").filter(Boolean).map((part, idx, arr) => (
            <span key={idx}>
              {" / "}
              <button onClick={() => navigateToFolder(arr.slice(0, idx + 1).join("/") + "/")}>
                {part}
              </button>
            </span>
          ))}
        </div>
        <button
          className="process-btn"
          onClick={() => onSelectPrefix(currentPrefix)}
          title={t("filesProcessFolder")}
          disabled={!portalSettings.processingEnabled}
        >
          {t("filesProcessFolder")}
        </button>
        <RestoreFromSnapshot currentPrefix={currentPrefix} />
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="file-list">
        {currentPrefix && (
          <div className="file-item folder" onClick={navigateUp}>
            <span className="icon">📁</span>
            <span className="name">..</span>
            <span className="size">-</span>
            <span className="modified">-</span>
          </div>
        )}

        {folders.map((folder) => (
          <div
            key={folder}
            className="file-item folder"
            onClick={() => navigateToFolder(folder)}
          >
            <span className="icon">📁</span>
            <span className="name">{folder.replace(currentPrefix, "").replace("/", "")}</span>
            <span className="size">-</span>
            <span className="modified">-</span>
          </div>
        ))}

        {regularFiles.map((file) => {
          const fileName = file.key.replace(currentPrefix, "");
          return (
            <div key={file.key} className="file-item">
              <FilePreview fileKey={file.key} fileName={fileName} onSelect={onFileSelect} />
              <ShareLink fileKey={file.key} fileName={fileName} />
              <span className="name">{fileName}</span>
              <span className="size">{formatSize(file.size)}</span>
              <span className="modified">
                {file.lastModified ? new Date(file.lastModified).toLocaleDateString() : "-"}
              </span>
            </div>
          );
        })}

        {files.length === 0 && !loading && (
          <div className="empty-state">{t("filesEmpty")}</div>
        )}
      </div>

      {loading && <div className="loading">{t("loading")}</div>}

      {hasMore && !loading && (
        <button
          className="load-more"
          onClick={() => loadFiles(currentPrefix, continuationToken)}
        >
          {t("filesLoadMore")}
        </button>
      )}
    </div>
  );
}
