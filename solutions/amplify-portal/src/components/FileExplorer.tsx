import { useState, useEffect, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { portalSettings } from "../portal-settings";
import { FilePreview } from "./FilePreview";
import { RestoreFromSnapshot } from "./RestoreFromSnapshot";
import { ShareLink } from "./ShareLink";
import { FavoriteButton } from "./Favorites";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

// Parse the JSON string response from generic dispatch endpoints
function parseResponse<T>(response: { data?: string | null }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === 'string' ? JSON.parse(response.data) : response.data;
  } catch { return null; }
}

interface FileExplorerProps {
  onSelectPrefix: (prefix: string) => void;
  onFileSelect?: (fileKey: string, fileName: string) => void;
  /**
   * Folder to open on mount and whenever the value changes. Lets other views
   * (favorites, recent, search, job results) hand a location to the explorer.
   */
  initialPrefix?: string;
  /**
   * Bumped by the caller on every navigation request so that asking for the
   * same folder twice still re-opens it, even after browsing elsewhere.
   */
  prefixNonce?: number;
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
export function FileExplorer({
  onSelectPrefix,
  onFileSelect,
  initialPrefix = "",
  prefixNonce = 0,
}: FileExplorerProps) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [currentPrefix, setCurrentPrefix] = useState(initialPrefix);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [continuationToken, setContinuationToken] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const { t } = useTranslation();

  /** PHI/PII path detection — blocks AI processing for regulated data folders */
  const isPhiPath = (path: string): boolean => {
    const lower = path.toLowerCase();
    return /\/(dicom|phi|pii|hipaa|protected-health)[\/-]/.test(`/${lower}`) ||
           lower.startsWith("dicom/") || lower.startsWith("phi/") || lower.startsWith("pii/");
  };

  const loadFiles = useCallback(async (prefix: string, token?: string | null) => {
    setLoading(true);
    setError(null);

    try {
      const response = await (client.queries as any).fileQuery({ action: "listFiles", params: JSON.stringify({
        prefix,
        maxKeys: 100,
        continuationToken: token || undefined,
      }) });
      const data = parseResponse<{ files?: FileItem[]; nextContinuationToken?: string; isTruncated?: boolean }>(response);

      if (data) {
        const newFiles = (data.files || []) as FileItem[];
        setFiles(token ? (prev) => [...prev, ...newFiles] : newFiles);
        setContinuationToken(data.nextContinuationToken || null);
        setHasMore(data.isTruncated || false);
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

  // Follow the location handed in by another view (favorites, recent, search,
  // job results). Keyed on prefixNonce as well as the prefix so that repeating
  // the same request re-opens the folder instead of doing nothing.
  useEffect(() => {
    setCurrentPrefix(initialPrefix);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPrefix, prefixNonce]);

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
          title={isPhiPath(currentPrefix) ? t("aiPhiBlocked") : t("filesProcessFolder")}
          disabled={!portalSettings.processingEnabled || isPhiPath(currentPrefix)}
        >
          {isPhiPath(currentPrefix) ? `🚫 ${t("aiPhiBlockedShort")}` : t("filesProcessFolder")}
        </button>
        <RestoreFromSnapshot currentPrefix={currentPrefix} />
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="file-list">
        {currentPrefix && (
          <div className="file-item folder" onClick={navigateUp}>
            <span className="file-item-actions">
              <span className="favorite-btn-spacer" aria-hidden="true" />
              <span className="icon">📁</span>
            </span>
            <span className="name">..</span>
            <span className="size">-</span>
            <span className="modified">-</span>
          </div>
        )}

        {folders.map((folder) => {
          const folderName = folder.replace(currentPrefix, "").replace("/", "");
          return (
            <div
              key={folder}
              className="file-item folder"
              onClick={() => navigateToFolder(folder)}
            >
              <span className="file-item-actions">
                <FavoriteButton fileKey={folder} fileName={folderName} />
                <span className="icon">📁</span>
              </span>
              <span className="name">{folderName}</span>
              <span className="size">-</span>
              <span className="modified">-</span>
            </div>
          );
        })}

        {regularFiles.map((file) => {
          const fileName = file.key.replace(currentPrefix, "");
          return (
            <div key={file.key} className="file-item">
              <span className="file-item-actions">
                <FavoriteButton fileKey={file.key} fileName={fileName} />
                <FilePreview fileKey={file.key} fileName={fileName} onSelect={onFileSelect} />
                <ShareLink fileKey={file.key} fileName={fileName} />
              </span>
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
