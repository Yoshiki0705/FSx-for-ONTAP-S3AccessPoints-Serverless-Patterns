import { useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { fileQuery } from "../lib/dispatch";
import { errorMessage } from "../lib/portalQuery";
import { portalSettings } from "../portal-settings";
import { FilePreview } from "./FilePreview";
import { RestoreFromSnapshot } from "./RestoreFromSnapshot";
import { ShareLink } from "./ShareLink";
import { FavoriteButton } from "./Favorites";
import { FolderDownload } from "./FolderDownload";
import { FileTagsBadges, FileTagsEditor } from "./FileTags";
import { AiMetadataBadges, useAiMetadata } from "./AiMetadataBadges";
import { SnapshotCompare } from "./SnapshotCompare";
import {
  FileRowActions,
  RestoreFromTrashButton,
  UploadLink,
  TRASH_PREFIX,
} from "./FileLifecycle";
import { useTranslation } from "../i18n";
import { isRegulatedPath } from "../utils/regulatedPath";

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

/** One page of a listing. Named so getNextPageParam can be annotated. */
interface FilePage {
  files: FileItem[];
  nextContinuationToken?: string;
  isTruncated: boolean;
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
  // Where the explorer is, plus the caller request it came from. Keeping the
  // honoured request alongside the location lets a prop change be detected
  // during render, so following the caller needs no effect and no extra pass.
  const [nav, setNav] = useState({
    prefix: initialPrefix,
    fromPrefix: initialPrefix,
    fromNonce: prefixNonce,
  });
  if (nav.fromNonce !== prefixNonce || nav.fromPrefix !== initialPrefix) {
    setNav({ prefix: initialPrefix, fromPrefix: initialPrefix, fromNonce: prefixNonce });
  }
  const currentPrefix = nav.prefix;
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

  // S3 continuation tokens are exactly what useInfiniteQuery models, so "load
  // more" appends a page instead of the loader concatenating onto local state.
  // Changing folder changes the key, which discards the accumulated pages.
  const {
    data,
    isFetching: loading,
    error: queryError,
    fetchNextPage,
    hasNextPage,
    refetch,
  } = useInfiniteQuery({
    queryKey: ["files", "listFiles", currentPrefix],
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: FilePage) =>
      last.isTruncated ? last.nextContinuationToken ?? undefined : undefined,
    queryFn: async ({ pageParam }): Promise<FilePage> => {
      const parsed = await fileQuery<{
        files?: FileItem[];
        nextContinuationToken?: string;
        isTruncated?: boolean;
      }>({
        action: "listFiles",
        params: {
          prefix: currentPrefix,
          maxKeys: 100,
          continuationToken: pageParam,
        },
      });
      return {
        files: (parsed?.files ?? []) as FileItem[],
        nextContinuationToken: parsed?.nextContinuationToken,
        isTruncated: parsed?.isTruncated ?? false,
      };
    },
  });

  const files = data?.pages.flatMap((p) => p.files) ?? [];
  const hasMore = hasNextPage;
  const error = errorMessage(queryError, "Failed to load files");

  // Trashed objects live under a prefix in the same bucket, so the trash is a
  // folder rather than a separate listing. Inside it, rename and trash make no
  // sense and restore does.
  const inTrash = currentPrefix.startsWith(TRASH_PREFIX);

  /** Discard the accumulated pages so a rename, trash or restore is reflected. */
  const reloadListing = () => void refetch();

  const navigateToFolder = (folderKey: string) => {
    setNav((prev) => ({ ...prev, prefix: folderKey }));
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

  // What AI processing recorded about the files on screen, in one batched call.
  const { data: aiMetadata } = useAiMetadata(regularFiles.map((f) => f.key));

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
          title={isRegulatedPath(currentPrefix) ? t("aiPhiBlocked") : t("filesProcessFolder")}
          disabled={!portalSettings.processingEnabled || isRegulatedPath(currentPrefix)}
        >
          {isRegulatedPath(currentPrefix) ? `🚫 ${t("aiPhiBlockedShort")}` : t("filesProcessFolder")}
        </button>
        <FolderDownload currentPrefix={currentPrefix} />
        <RestoreFromSnapshot currentPrefix={currentPrefix} />
        <UploadLink destinationPrefix={currentPrefix} />
        <button
          className={`trash-btn ${inTrash ? "active" : ""}`}
          onClick={() => navigateToFolder(inTrash ? "" : TRASH_PREFIX)}
          title={inTrash ? t("flLeaveTrash") : t("flOpenTrash")}
          aria-pressed={inTrash}
        >
          🗑️ {inTrash ? t("flLeaveTrash") : t("flOpenTrash")}
        </button>
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
                  {inTrash ? (
                    <RestoreFromTrashButton trashKey={file.key} onChanged={reloadListing} />
                  ) : (
                    <FileRowActions
                      fileKey={file.key}
                      fileName={fileName}
                      currentPrefix={currentPrefix}
                      onChanged={reloadListing}
                    />
                  )}
                </span>
                <span className="name">
                  {fileName}
                  <FileTagsBadges fileKey={file.key} refreshKey={tagRefresh} />
                  <AiMetadataBadges metadata={aiMetadata?.get(file.key)} />
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
          onClick={() => void fetchNextPage()}
        >
          {t("filesLoadMore")}
        </button>
      )}
    </div>
  );
}
