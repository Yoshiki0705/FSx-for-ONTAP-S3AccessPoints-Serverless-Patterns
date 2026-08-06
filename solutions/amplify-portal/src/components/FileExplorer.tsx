import { useState, useEffect, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { portalSettings } from "../portal-settings";
import { FilePreview } from "./FilePreview";
import { RestoreFromSnapshot } from "./RestoreFromSnapshot";
import { ShareLink } from "./ShareLink";
import { FavoriteButton } from "./Favorites";
import { FolderDownload } from "./FolderDownload";
import { FileTagsBadges, FileTagsEditor } from "./FileTags";
import { SnapshotCompare } from "./SnapshotCompare";
import { useTranslation } from "../i18n";
import { parseResponse } from "../utils/parseResponse";

const client = generateClient<Schema>();

// Parse the JSON string response from generic dispatch endpoints

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
  // Only one tag editor is open at a time, keyed by file key.
  const [tagEditorFor, setTagEditorFor] = useState<string | null>(null);
  // Bumped after a tag edit so the row badges reload.
  const [tagRefresh, setTagRefresh] = useState(0);
  // Snapshot comparison needs the clone's S3 Access Point alias, which the
  // restore job reports asynchronously, so it is entered here.
  const [showCompare, setShowCompare] = useState(false);
  const [cloneAliasDraft, setCloneAliasDraft] = useState("");
  const [cloneAlias, setCloneAlias] = useState("");
  const { t } = useTranslation();

  /** PHI/PII path detection — blocks AI processing for regulated data folders */
  const isPhiPath = (path: string): boolean => {
    const lower = path.toLowerCase();
    return /\/(dicom|phi|pii|hipaa|protected-health)[/-]/.test(`/${lower}`) ||
           lower.startsWith("dicom/") || lower.startsWith("phi/") || lower.startsWith("pii/");
  };

  const loadFiles = useCallback(async (prefix: string, token?: string | null) => {
    setLoading(true);
    setError(null);

    try {
      const response = await client.queries.fileQuery({ action: "listFiles", params: JSON.stringify({
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
        <FolderDownload currentPrefix={currentPrefix} />
        <RestoreFromSnapshot currentPrefix={currentPrefix} />
        <button
          className="compare-btn"
          onClick={() => setShowCompare((v) => !v)}
          title={showCompare ? t("scClose") : t("scCompare")}
          aria-expanded={showCompare}
        >
          🔍 {showCompare ? t("scClose") : t("scCompare")}
        </button>
      </div>

      {showCompare && (
        <div className="snapshot-compare-launcher">
          <label htmlFor="clone-ap-alias">{t("scCloneAlias")}</label>
          <input
            id="clone-ap-alias"
            type="text"
            value={cloneAliasDraft}
            onChange={(e) => setCloneAliasDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") setCloneAlias(cloneAliasDraft.trim());
            }}
            placeholder="fsxn-clone-ap-..."
          />
          <button
            className="rm-btn-primary"
            onClick={() => setCloneAlias(cloneAliasDraft.trim())}
            disabled={!cloneAliasDraft.trim()}
          >
            {t("scCompare")}
          </button>
          <p className="rm-hint">{t("scCloneAliasHint")}</p>
          {cloneAlias && (
            <SnapshotCompare cloneApAlias={cloneAlias} cloneLabel={cloneAlias} />
          )}
        </div>
      )}

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
          const tagsOpen = tagEditorFor === file.key;
          return (
            <div key={file.key} className="file-row">
              <div className="file-item">
                <span className="file-item-actions">
                  <FavoriteButton fileKey={file.key} fileName={fileName} />
                  <FilePreview fileKey={file.key} fileName={fileName} onSelect={onFileSelect} />
                  <ShareLink fileKey={file.key} fileName={fileName} />
                  <button
                    className={`tag-toggle ${tagsOpen ? "active" : ""}`}
                    onClick={() => setTagEditorFor(tagsOpen ? null : file.key)}
                    title={t("tagsEdit")}
                    aria-label={t("tagsEdit")}
                    aria-expanded={tagsOpen}
                  >
                    🏷️
                  </button>
                </span>
                <span className="name">
                  {fileName}
                  <FileTagsBadges fileKey={file.key} refreshKey={tagRefresh} />
                </span>
                <span className="size">{formatSize(file.size)}</span>
                <span className="modified">
                  {file.lastModified ? new Date(file.lastModified).toLocaleDateString() : "-"}
                </span>
              </div>
              {tagsOpen && (
                <FileTagsEditor
                  fileKey={file.key}
                  onChange={() => setTagRefresh((n) => n + 1)}
                />
              )}
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
