import { useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { fileQuery, fileMutate } from "../lib/dispatch";
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
import { RowMenu } from "./RowMenu";
import {
  CopyMoveButton,
  CreateFolderButton,
  DeleteForeverButton,
  FileRowActions,
  RestoreFromTrashButton,
  UploadLink,
  TRASH_PREFIX,
} from "./FileLifecycle";
import { useTranslation } from "../i18n";
import { useToast } from "../lib/toast";
import { isRegulatedPath } from "../utils/regulatedPath";
import { formatAbsoluteTime, formatRelativeTime } from "../utils/formatTime";
import { useThumbnails } from "../hooks/useThumbnails";

interface FileExplorerProps {
  onSelectPrefix: (prefix: string) => void;
  onFileSelect?: (fileKey: string, fileName: string) => void;
  /**
   * Called with the folder the explorer moved to, so the shell can put it in the
   * URL. Without this the location lives only here and a folder cannot be linked
   * to, bookmarked, or returned to with the back button.
   */
  onNavigate?: (prefix: string) => void;
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

/** A column the listing can be ordered by. */
type SortKey = "name" | "size" | "modified";

/** Which column orders the listing, and which way. */
interface Sort {
  key: SortKey;
  dir: "asc" | "desc";
}

/** The listing as the Access Point returns it: by key, ascending. */
const DEFAULT_SORT: Sort = { key: "name", dir: "asc" };

/** Stands in for a selection belonging to another folder. Shared to keep identity stable. */
const EMPTY_SELECTION: ReadonlySet<string> = new Set();

/**
 * Compare two rows on one column, ascending.
 *
 * Keys are compared rather than display names: every row in a listing shares the
 * current prefix, so the two orders are the same and the key needs no slicing.
 * Numeric collation is what makes `part2` precede `part10`, which is the order a
 * person reading a directory of numbered files expects.
 *
 * A row missing a size or a timestamp sorts as the smallest value, so it collects
 * at one end instead of scattering. Folders never reach here — the listing has
 * neither figure for them, so they are ordered by name.
 */
function compareOn(sort: Sort, locale: string): (a: FileItem, b: FileItem) => number {
  const ascending = (a: FileItem, b: FileItem): number => {
    switch (sort.key) {
      case "size":
        return (a.size ?? -1) - (b.size ?? -1);
      case "modified":
        return (a.lastModified ? Date.parse(a.lastModified) : -1) -
          (b.lastModified ? Date.parse(b.lastModified) : -1);
      default:
        return a.key.localeCompare(b.key, locale, { numeric: true, sensitivity: "base" });
    }
  };
  return sort.dir === "asc" ? ascending : (a, b) => ascending(b, a);
}

/** The last segment of a key, which is what the row shows. */
function displayName(key: string, prefix: string): string {
  return key.replace(prefix, "");
}

/**
 * File Explorer component.
 *
 * Displays files from FSx for ONTAP volume via S3 Access Point.
 * Supports:
 * - Directory navigation (prefix-based)
 * - Pagination (1000 objects per page)
 * - File selection for processing
 * - Ordering, filtering and multi-select over the rows loaded so far
 */
export function FileExplorer({
  onSelectPrefix,
  onFileSelect,
  onNavigate,
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
  // `nav.prefix !== initialPrefix` is what keeps this from firing on the explorer's
  // own moves: reporting a navigation upwards changes the prop back to the folder
  // already open, and following that would be a second render for no change. A
  // caller asking for the same folder again still arrives, because that carries a
  // new nonce.
  if (
    nav.fromNonce !== prefixNonce ||
    (nav.fromPrefix !== initialPrefix && nav.prefix !== initialPrefix)
  ) {
    setNav({ prefix: initialPrefix, fromPrefix: initialPrefix, fromNonce: prefixNonce });
  }
  const currentPrefix = nav.prefix;
  // Ordering outlives a move between folders, the way a chosen column does in a
  // file manager. Filter and selection do not — see `view` below.
  const [sort, setSort] = useState<Sort>(DEFAULT_SORT);
  // Filter text, selection, and the anchor a shift-click extends from, tagged with
  // the folder they were made in. Tagging rather than clearing on navigation means
  // a selection made in one folder can never be acted on in another: the tag stops
  // matching and the state is ignored, with no effect to fire and no window in
  // which the stale set is still live.
  const [view, setView] = useState<{
    prefix: string;
    filter: string;
    selected: ReadonlySet<string>;
    anchor: number | null;
  }>({ prefix: currentPrefix, filter: "", selected: new Set(), anchor: null });
  const scoped = view.prefix === currentPrefix ? view : null;
  const filterText = scoped?.filter ?? "";
  const selectedKeys = scoped?.selected ?? EMPTY_SELECTION;
  // Progress and per-file outcome of a bulk operation. Failures are kept by name
  // because "3 of 20 failed" does not tell anyone which three to retry.
  const [bulk, setBulk] = useState<{
    busy: boolean;
    done: number;
    total: number;
    failures: { name: string; error: string }[];
  }>({ busy: false, done: 0, total: 0, failures: [] });
  // Only one tag editor is open at a time, keyed by file key.
  const [tagEditorFor, setTagEditorFor] = useState<string | null>(null);
  // Bumped after a tag edit so the row badges reload.
  const [tagRefresh, setTagRefresh] = useState(0);
  // Snapshot comparison needs the clone's S3 Access Point alias, which the
  // restore job reports asynchronously, so it is entered here.
  const [showCompare, setShowCompare] = useState(false);
  const [cloneAliasDraft, setCloneAliasDraft] = useState("");
  const [cloneAlias, setCloneAlias] = useState("");
  const { t, locale } = useTranslation();
  const { notify } = useToast();

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
    onNavigate?.(folderKey);
  };

  const navigateUp = () => {
    const parts = currentPrefix.split("/").filter(Boolean);
    parts.pop();
    const parentPrefix = parts.length > 0 ? parts.join("/") + "/" : "";
    navigateToFolder(parentPrefix);
  };

  // Separate folders (common prefixes) from files
  const allFolders = files
    .filter((f) => f.storageClass === "DIRECTORY" || f.key.endsWith("/"))
    .map((f) => f.key);
  const allFiles = files.filter(
    (f) => f.storageClass !== "DIRECTORY" && !f.key.endsWith("/")
  );

  // Filtering and ordering happen here, over the pages fetched so far, because
  // ListObjectsV2 offers neither: it returns keys in ascending order and takes a
  // prefix, not a substring or a sort column. Anything else has to be arranged on
  // what is in hand, and the header says so while pages remain — otherwise
  // "largest first" would read as a claim about the folder rather than about the
  // rows on screen.
  const needle = filterText.trim().toLowerCase();
  const matches = (key: string) =>
    needle === "" || displayName(key, currentPrefix).toLowerCase().includes(needle);

  const folders = allFolders
    .filter(matches)
    .sort((a, b) => a.localeCompare(b, locale, { numeric: true, sensitivity: "base" }));
  const regularFiles = allFiles.filter((f) => matches(f.key)).sort(compareOn(sort, locale));
  const hiddenByFilter = allFolders.length + allFiles.length - folders.length - regularFiles.length;
  // One request for the page, keyed on the image keys it contains. Asking per
  // row would cost an invocation per row and then make the browser fetch each
  // full-size original to draw something the width of a fingertip.
  const { urlFor: thumbnailFor } = useThumbnails(regularFiles.map((file) => file.key));

  // What AI processing recorded about the files loaded, in one batched call. Asked
  // for the unfiltered set on purpose: keying this on the filtered set would issue
  // a fresh query on every keystroke in the filter box, and the badges are looked
  // up by key, so entries for hidden rows cost nothing.
  const { data: aiMetadata } = useAiMetadata(allFiles.map((f) => f.key));

  /** Order by a column, or reverse it when it already orders the listing. */
  const sortBy = (key: SortKey) => {
    setSort((prev) =>
      prev.key === key ? { key, dir: prev.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }
    );
  };

  /** Replace the folder-scoped view state, re-tagging it with the current folder. */
  const updateView = (changes: Partial<Omit<typeof view, "prefix">>) => {
    setView({
      prefix: currentPrefix,
      filter: filterText,
      selected: selectedKeys,
      anchor: scoped?.anchor ?? null,
      ...changes,
    });
  };

  /**
   * Add or remove one row, or the run between the anchor and this row.
   *
   * The run is taken from the rows as displayed, so it follows the current order
   * and skips what the filter hides — a shift-click selects what was swept over on
   * screen, not an interval of the underlying listing.
   */
  const toggleSelection = (index: number, extendFromAnchor: boolean) => {
    const anchor = scoped?.anchor;
    const run =
      extendFromAnchor && anchor !== null && anchor !== undefined
        ? regularFiles.slice(Math.min(anchor, index), Math.max(anchor, index) + 1)
        : [regularFiles[index]];
    const selecting = !selectedKeys.has(regularFiles[index].key);
    const next = new Set(selectedKeys);
    for (const file of run) {
      if (selecting) next.add(file.key);
      else next.delete(file.key);
    }
    updateView({ selected: next, anchor: index });
  };

  const allVisibleSelected =
    regularFiles.length > 0 && regularFiles.every((f) => selectedKeys.has(f.key));
  const someVisibleSelected = regularFiles.some((f) => selectedKeys.has(f.key));

  const toggleSelectAll = () => {
    updateView({
      selected: allVisibleSelected ? new Set() : new Set(regularFiles.map((f) => f.key)),
      anchor: null,
    });
  };

  /**
   * Trash or restore every selected file, one call at a time.
   *
   * Serial rather than concurrent, and one round trip per file, because the
   * backend has no bulk action: `trashFile` copies a single object and deletes the
   * original. Firing them together would multiply that by the selection size
   * against one Lambda. The proper fix is an action that takes a list; until there
   * is one, the progress count is here so a long run does not look stalled.
   */
  const runBulk = async () => {
    const targets = regularFiles.filter((f) => selectedKeys.has(f.key));
    if (targets.length === 0) return;
    const question = inTrash ? t("filesBulkRestoreConfirm") : t("filesBulkTrashConfirm");
    if (!window.confirm(question.replace("{n}", String(targets.length)))) return;

    const failures: { name: string; error: string }[] = [];
    // Keys of the objects that did move, so the run can be put back. Collected
    // from the responses rather than derived from the selection: a partial run
    // must undo what happened, not what was asked for.
    const moved: string[] = [];
    setBulk({ busy: true, done: 0, total: targets.length, failures: [] });
    for (const [index, file] of targets.entries()) {
      const name = displayName(file.key, currentPrefix);
      try {
        const res = inTrash
          ? await fileMutate<{ success?: boolean; restoredKey?: string; error?: string }>({
              action: "restoreFromTrash",
              params: { trashKey: file.key },
            })
          : await fileMutate<{ success?: boolean; trashKey?: string; error?: string }>({
              action: "trashFile",
              params: { key: file.key },
            });
        if (!res?.success) {
          failures.push({ name, error: res?.error || t("filesBulkItemFailed") });
        } else {
          const landed = inTrash
            ? (res as { restoredKey?: string }).restoredKey
            : (res as { trashKey?: string }).trashKey;
          if (landed) moved.push(landed);
        }
      } catch (e) {
        failures.push({ name, error: e instanceof Error ? e.message : t("filesBulkItemFailed") });
      }
      setBulk({ busy: true, done: index + 1, total: targets.length, failures: [...failures] });
    }
    setBulk({ busy: false, done: targets.length, total: targets.length, failures });
    updateView({ selected: new Set(), anchor: null });
    reloadListing();

    if (moved.length > 0) {
      notify({
        tone: "success",
        message: t(inTrash ? "filesBulkRestoredNotice" : "filesBulkTrashedNotice").replace(
          "{n}",
          String(moved.length)
        ),
        action: {
          label: t("toastUndo"),
          run: async () => {
            // Serial for the same reason the forward run is, and it reports the
            // first refusal rather than continuing quietly: a partly undone bulk
            // move is worse than one that stopped and said where.
            for (const key of moved) {
              const back = inTrash
                ? await fileMutate<{ success?: boolean; error?: string }>({
                    action: "trashFile",
                    params: { key },
                  })
                : await fileMutate<{ success?: boolean; error?: string }>({
                    action: "restoreFromTrash",
                    params: { trashKey: key },
                  });
              if (!back?.success) throw new Error(back?.error || t("filesBulkItemFailed"));
            }
            reloadListing();
          },
        },
      });
    }
  };

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
        <input
          className="file-filter"
          type="search"
          value={filterText}
          onChange={(e) => updateView({ filter: e.target.value })}
          placeholder={t("filesFilterPlaceholder")}
          aria-label={t("filesFilterLabel")}
        />
        <button
          className="process-btn"
          onClick={() => onSelectPrefix(currentPrefix)}
          title={isRegulatedPath(currentPrefix) ? t("aiPhiBlocked") : t("filesProcessFolder")}
          disabled={!portalSettings.processingEnabled || isRegulatedPath(currentPrefix)}
        >
          {isRegulatedPath(currentPrefix) ? `🚫 ${t("aiPhiBlockedShort")}` : t("filesProcessFolder")}
        </button>
        {/* Not offered inside the trash: a folder created there would be a place to
            put things that the restore path has no meaning for. */}
        {!inTrash && (
          <CreateFolderButton currentPrefix={currentPrefix} onChanged={reloadListing} />
        )}
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

      {selectedKeys.size > 0 && (
        <div className="file-bulk-bar">
          <span className="file-bulk-count">
            {t("filesSelectedCount").replace("{n}", String(selectedKeys.size))}
          </span>
          <button
            className="rm-btn-primary"
            onClick={() => void runBulk()}
            disabled={bulk.busy}
            // Named with the count because every row carries a button reading
            // "Move to trash" too. Read aloud, the short label gave a screen
            // reader user several identical buttons and no way to tell the one
            // acting on the whole selection from the one acting on a row.
            aria-label={t(inTrash ? "filesBulkRestoreLabel" : "filesBulkTrashLabel").replace(
              "{n}",
              String(selectedKeys.size)
            )}
          >
            {inTrash ? `♻️ ${t("filesBulkRestore")}` : `🗑️ ${t("filesBulkTrash")}`}
          </button>
          <button
            className="rm-btn-sm"
            onClick={() => updateView({ selected: new Set(), anchor: null })}
            disabled={bulk.busy}
          >
            {t("filesClearSelection")}
          </button>
          {bulk.busy && (
            <span className="file-bulk-progress" role="status">
              {t("filesBulkProgress")
                .replace("{done}", String(bulk.done))
                .replace("{total}", String(bulk.total))}
            </span>
          )}
        </div>
      )}

      {!bulk.busy && bulk.failures.length > 0 && (
        <div className="error-message" role="alert">
          <p>
            {t("filesBulkPartialFailure")
              .replace("{failed}", String(bulk.failures.length))
              .replace("{total}", String(bulk.total))}
          </p>
          <ul className="file-bulk-failures">
            {bulk.failures.map((f) => (
              <li key={f.name}>
                <code>{f.name}</code>: {f.error}
              </li>
            ))}
          </ul>
        </div>
      )}

      {hasMore && (needle !== "" || sort.key !== DEFAULT_SORT.key || sort.dir !== DEFAULT_SORT.dir) && (
        <p className="file-scope-note">
          {t("filesLoadedScopeNote").replace("{n}", String(files.length))}
        </p>
      )}

      <div className="file-list">
        <div className="file-list-header">
          <span className="file-item-actions">
            <input
              type="checkbox"
              className="file-select"
              checked={allVisibleSelected}
              // No ARIA state for "some but not all", so the box itself carries it.
              ref={(el) => {
                if (el) el.indeterminate = someVisibleSelected && !allVisibleSelected;
              }}
              onChange={toggleSelectAll}
              disabled={regularFiles.length === 0 || bulk.busy}
              aria-label={t("filesSelectAll")}
            />
          </span>
          <SortHeader column="name" label={t("filesColumnName")} sort={sort} onSort={sortBy} />
          <SortHeader column="size" label={t("filesColumnSize")} sort={sort} onSort={sortBy} />
          <SortHeader
            column="modified"
            label={t("filesColumnModified")}
            sort={sort}
            onSort={sortBy}
          />
        </div>

        {/* The row stays a plain container and the name carries the control.
            Making the row itself `role="button"` did reach the keyboard, but it
            nested the favourite star inside another control and took its label
            into the row's accessible name, which came out as "Add to favourites
            📁 ai-outputs - -". A button on the name is announced as the folder it
            opens, and the star beside it stays a control of its own. Clicking
            anywhere in the row still works, which is the pointer affordance every
            file manager has. */}
        {currentPrefix && (
          <div className="file-item folder" onClick={navigateUp}>
            <span className="file-item-actions">
              <span className="file-select-spacer" aria-hidden="true" />
              <span className="favorite-btn-spacer" aria-hidden="true" />
              <span className="icon">📁</span>
            </span>
            <span className="name">
              <button
                className="file-name-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  navigateUp();
                }}
                aria-label={t("filesGoUp")}
              >
                ..
              </button>
            </span>
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
                {/* Folders are not selectable: trashFile copies and deletes one
                    object, so sending it a prefix would leave the contents behind. */}
                <span className="file-select-spacer" aria-hidden="true" />
                <FavoriteButton fileKey={folder} fileName={folderName} />
                <span className="icon">📁</span>
              </span>
              <span className="name">
                <button
                  className="file-name-btn"
                  // Stops the row handler from running a second time. Enter and
                  // Space need no handler of their own: a button fires a click.
                  onClick={(e) => {
                    e.stopPropagation();
                    navigateToFolder(folder);
                  }}
                >
                  {folderName}
                </button>
              </span>
              <span className="size">-</span>
              <span className="modified">-</span>
            </div>
          );
        })}

        {regularFiles.map((file, index) => {
          const fileName = displayName(file.key, currentPrefix);
          const tagsOpen = tagEditorFor === file.key;
          const selected = selectedKeys.has(file.key);
          return (
            <div key={file.key} className={`file-row ${selected ? "selected" : ""}`}>
              <div className="file-item">
                <span className="file-item-actions">
                  <input
                    type="checkbox"
                    className="file-select"
                    checked={selected}
                    // Shift is read from the native event because a checkbox's
                    // change comes from a click that carries the modifier, while
                    // React's ChangeEvent does not expose it. Toggling with the
                    // keyboard produces a click with no modifier, so a keyboard
                    // user selects one row at a time rather than an unintended run.
                    onChange={(e) =>
                      toggleSelection(
                        index,
                        e.nativeEvent instanceof MouseEvent && e.nativeEvent.shiftKey
                      )
                    }
                    disabled={bulk.busy}
                    aria-label={t("filesSelectRow").replace("{name}", fileName)}
                  />
                  <FavoriteButton fileKey={file.key} fileName={fileName} />
                  {/* Preview stays in the row: it is how a file is opened, which is
                      what most rows are clicked for. The rest move behind the
                      overflow button, because seven controls on every line are read
                      before the filename is. */}
                  <FilePreview
                    fileKey={file.key}
                    fileName={fileName}
                    onSelect={onFileSelect}
                    thumbnailUrl={thumbnailFor(file.key)}
                  />
                  <RowMenu fileName={fileName}>
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
                      <>
                        <RestoreFromTrashButton trashKey={file.key} onChanged={reloadListing} />
                        {/* Only offered inside the trash, which is also the only
                            place the backend accepts it. */}
                        <DeleteForeverButton
                          trashKey={file.key}
                          fileName={fileName}
                          onChanged={reloadListing}
                        />
                      </>
                    ) : (
                      <>
                        <CopyMoveButton
                          fileKey={file.key}
                          fileName={fileName}
                          currentPrefix={currentPrefix}
                          onChanged={reloadListing}
                        />
                        <FileRowActions
                          fileKey={file.key}
                          fileName={fileName}
                          currentPrefix={currentPrefix}
                          onChanged={reloadListing}
                        />
                      </>
                    )}
                  </RowMenu>
                </span>
                <span className="name">
                  {fileName}
                  <FileTagsBadges fileKey={file.key} refreshKey={tagRefresh} />
                  <AiMetadataBadges metadata={aiMetadata?.get(file.key)} />
                </span>
                <span
                  className="size"
                  // The rounded figure loses the difference between 1.4 MB and
                  // 1.44 MB, which matters when comparing two versions of a file.
                  title={file.size === null ? undefined : `${file.size.toLocaleString(locale)} B`}
                >
                  {formatSize(file.size)}
                </span>
                <span className="modified" title={formatAbsoluteTime(file.lastModified, locale)}>
                  {formatRelativeTime(file.lastModified, locale)}
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

        {/* The folder is not empty, the filter is hiding all of it. Saying "no
            files in this directory" here would be wrong and would hide the cause. */}
        {files.length > 0 && folders.length === 0 && regularFiles.length === 0 && (
          <div className="empty-state">
            {t("filesFilterNoMatch").replace("{n}", String(hiddenByFilter))}
          </div>
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

/**
 * One clickable column heading.
 *
 * Deliberately not marked up with `role="columnheader"` and `aria-sort`: the rows
 * below are a CSS grid of divs, not cells, so claiming a table here would describe
 * a structure a screen reader would then fail to find. The direction is in the
 * button's accessible name instead, which is true of what is actually there.
 */
function SortHeader({
  column,
  label,
  sort,
  onSort,
}: {
  column: SortKey;
  label: string;
  sort: Sort;
  onSort: (key: SortKey) => void;
}) {
  const { t } = useTranslation();
  const active = sort.key === column;
  const indicator = active ? (sort.dir === "asc" ? "▲" : "▼") : "";
  return (
    <button
      className={`file-sort-btn ${column} ${active ? "active" : ""}`}
      onClick={() => onSort(column)}
      aria-label={
        active
          ? `${label} — ${t(sort.dir === "asc" ? "filesSortAscending" : "filesSortDescending")}`
          : `${label} — ${t("filesSortBy")}`
      }
    >
      {label}
      <span className="file-sort-indicator" aria-hidden="true">
        {indicator}
      </span>
    </button>
  );
}
