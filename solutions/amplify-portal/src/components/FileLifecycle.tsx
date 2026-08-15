import { useState } from "react";
import { fileMutate } from "../lib/dispatch";
import { useTranslation } from "../i18n";
import { useToast } from "../lib/toast";

/** Prefix the backend moves trashed objects under. Mirrors functions/list-files. */
export const TRASH_PREFIX = ".trash/";

interface RowActionsProps {
  fileKey: string;
  fileName: string;
  /** Current folder, so a rename can keep the file where it is. */
  currentPrefix: string;
  /** Called after a change that alters the listing. */
  onChanged: () => void;
}

/**
 * Rename and trash controls for one row of the explorer.
 *
 * Both operations are copy-then-delete on the S3 Access Point, not an ONTAP
 * rename: the object is rewritten under the new key. That is cheap for small
 * files and not cheap for large ones, which is why the confirm text says so
 * rather than presenting it as a metadata change.
 */
export function FileRowActions({ fileKey, fileName, currentPrefix, onChanged }: RowActionsProps) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(fileName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submitRename = async () => {
    const next = draft.trim();
    // A rename to the same name is not an error worth reporting, just a no-op.
    if (!next || next === fileName) { setRenaming(false); return; }
    // Renaming is within the current folder. A name carrying a slash would move
    // the file somewhere the user did not navigate to, so it is refused.
    if (next.includes("/")) { setError(t("flRenameNoSlash")); return; }
    setBusy(true);
    setError(null);
    try {
      const destinationKey = `${currentPrefix}${next}`;
      const res = await fileMutate<{ success?: boolean; newKey?: string; error?: string }>({
        action: "renameFile",
        params: { sourceKey: fileKey, destinationKey },
      });
      if (res?.success) {
        setRenaming(false);
        onChanged();
        notify({
          tone: "success",
          message: t("flRenamedNotice").replace("{from}", fileName).replace("{to}", next),
          // A rename is a rename in the other direction, so the reversal is the
          // same call with the keys swapped.
          action: {
            label: t("toastUndo"),
            run: async () => {
              const undone = await fileMutate<{ success?: boolean; error?: string }>({
                action: "renameFile",
                params: { sourceKey: destinationKey, destinationKey: fileKey },
              });
              if (!undone?.success) throw new Error(undone?.error || t("flRenameFailed"));
              onChanged();
            },
          },
        });
      } else {
        setError(res?.error || t("flRenameFailed"));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("flRenameFailed"));
    } finally {
      setBusy(false);
    }
  };

  const trash = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fileMutate<{ success?: boolean; trashKey?: string; error?: string }>({
        action: "trashFile",
        params: { key: fileKey },
      });
      if (res?.success) {
        onChanged();
        // No confirmation dialog in front of this any more. A dialog asks before
        // the fact and asks every time; the undo answers after, when the mistake
        // is visible, and the object is still there to put back.
        notify({
          tone: "success",
          message: t("flTrashedNotice").replace("{name}", fileName),
          action: res.trashKey
            ? {
                label: t("toastUndo"),
                run: async () => {
                  const undone = await fileMutate<{ success?: boolean; error?: string }>({
                    action: "restoreFromTrash",
                    params: { trashKey: res.trashKey },
                  });
                  if (!undone?.success) throw new Error(undone?.error || t("flRestoreFailed"));
                  onChanged();
                },
              }
            : undefined,
        });
      } else {
        setError(res?.error || t("flTrashFailed"));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("flTrashFailed"));
    } finally {
      setBusy(false);
    }
  };

  if (renaming) {
    return (
      <span className="fl-rename">
        <input
          type="text"
          value={draft}
          autoFocus
          disabled={busy}
          aria-label={t("flRename")}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void submitRename();
            if (e.key === "Escape") { setRenaming(false); setError(null); }
          }}
        />
        <button className="rm-btn-sm" onClick={() => void submitRename()} disabled={busy}>
          {busy ? "…" : t("flRenameSave")}
        </button>
        <button className="rm-btn-sm" onClick={() => { setRenaming(false); setError(null); }} disabled={busy}>
          {t("flCancel")}
        </button>
        {error && <span className="fl-error">{error}</span>}
      </span>
    );
  }

  return (
    <>
      <button
        className="fl-btn"
        onClick={() => { setDraft(fileName); setRenaming(true); }}
        title={t("flRename")}
        aria-label={t("flRename")}
      >
        ✏️
      </button>
      <button
        className="fl-btn"
        onClick={() => void trash()}
        disabled={busy}
        title={t("flTrash")}
        aria-label={t("flTrash")}
      >
        🗑️
      </button>
      {error && <span className="fl-error">{error}</span>}
    </>
  );
}

interface RestoreProps {
  /** Key under `.trash/`, as listed by browsing into the trash folder. */
  trashKey: string;
  onChanged: () => void;
}

/** Restore control, shown instead of rename/trash while inside `.trash/`. */
export function RestoreFromTrashButton({ trashKey, onChanged }: RestoreProps) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const restore = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fileMutate<{ success?: boolean; restoredKey?: string; error?: string }>({
        action: "restoreFromTrash",
        params: { trashKey },
      });
      if (res?.success) {
        onChanged();
        // Says where it went. The row leaves the trash listing on restore, so
        // without the destination there is nothing on screen to tell the user
        // which folder to look in.
        notify({
          tone: "success",
          message: t("flRestoredNotice").replace(
            "{key}",
            res.restoredKey || trashKey.replace(TRASH_PREFIX, "")
          ),
        });
      } else {
        setError(res?.error || t("flRestoreFailed"));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("flRestoreFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        className="fl-btn"
        onClick={() => void restore()}
        disabled={busy}
        title={t("flRestore")}
        aria-label={t("flRestore")}
      >
        {busy ? "…" : "♻️"}
      </button>
      {error && <span className="fl-error">{error}</span>}
    </>
  );
}

interface UploadLinkProps {
  /** Folder the uploaded file lands in. */
  destinationPrefix: string;
}

const TTL_CHOICES = [
  { labelKey: "flTtl1h", seconds: 3600 },
  { labelKey: "flTtl24h", seconds: 86400 },
] as const;

/**
 * Produce a presigned PUT URL so someone without portal access can upload one
 * file into this folder.
 *
 * The URL is the credential. Anyone holding it can write to exactly that key
 * until it expires, which is why the UI states the destination key and the
 * expiry next to the link rather than only offering a copy button.
 */
export function UploadLink({ destinationPrefix }: UploadLinkProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [fileName, setFileName] = useState("");
  const [ttl, setTtl] = useState<number>(3600);
  const [url, setUrl] = useState("");
  const [destKey, setDestKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const create = async () => {
    setBusy(true);
    setError(null);
    setUrl("");
    try {
      const res = await fileMutate<{
        uploadUrl?: string;
        destinationKey?: string;
        error?: string;
      }>({
        action: "createUploadLink",
        params: {
          destinationPrefix: destinationPrefix || "uploads/",
          fileName: fileName.trim(),
          expiresIn: ttl,
        },
      });
      if (res?.uploadUrl) {
        setUrl(res.uploadUrl);
        setDestKey(res.destinationKey || "");
      } else {
        setError(res?.error || t("flUploadLinkFailed"));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("flUploadLinkFailed"));
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fl-upload-link">
      <button className="upload-link-btn" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        📤 {t("flUploadLink")}
      </button>
      {open && (
        <div className="fl-upload-panel">
          <p className="rm-hint">{t("flUploadLinkHint")}</p>
          <label htmlFor="fl-upload-name">{t("flUploadFileName")}</label>
          <input
            id="fl-upload-name"
            type="text"
            value={fileName}
            onChange={(e) => setFileName(e.target.value)}
            placeholder={t("flUploadFileNamePlaceholder")}
          />
          <div className="fl-ttl">
            {TTL_CHOICES.map((c) => (
              <button
                key={c.seconds}
                className={`rm-btn-sm ${ttl === c.seconds ? "active" : ""}`}
                onClick={() => setTtl(c.seconds)}
                aria-pressed={ttl === c.seconds}
              >
                {t(c.labelKey)}
              </button>
            ))}
          </div>
          <button className="rm-btn-primary" onClick={() => void create()} disabled={busy}>
            {busy ? t("loading") : t("flUploadLinkCreate")}
          </button>
          {error && <div className="error-message">{error}</div>}
          {url && (
            <div className="fl-upload-result">
              <p className="rm-hint">
                {t("flUploadDestination")}: <code>{destKey}</code>
              </p>
              <textarea readOnly value={url} rows={3} aria-label={t("flUploadLink")} />
              <button className="rm-btn-sm" onClick={() => void copy()}>
                {copied ? t("flCopied") : t("flCopy")}
              </button>
              {/* The URL is signed for PUT. Opening it in a browser sends GET and
                  S3 answers SignatureDoesNotMatch, because the method is part of
                  what was signed. Measured on an iPhone, where the link looked
                  tappable and produced a wall of XML. Give the recipient the
                  command instead of a link they cannot use. */}
              <p className="rm-hint">{t("flUploadLinkPutOnly")}</p>
              <p className="rm-hint">{t("flUploadLinkCurlLabel")}</p>
              <textarea
                readOnly
                rows={2}
                className="fl-upload-curl"
                aria-label={t("flUploadLinkCurlLabel")}
                value={`curl -X PUT --upload-file <file> "${url}"`}
              />
              <p className="rm-hint">{t("flUploadLinkSelfHint")}</p>
              <p className="fl-warning">{t("flUploadLinkWarning")}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface CreateFolderProps {
  /** Folder the new one is created inside. */
  currentPrefix: string;
  onChanged: () => void;
}

/**
 * Create a folder in the current location.
 *
 * S3 has no directories. What this makes is a zero-byte object whose key ends in
 * "/", which is what causes the listing to report it as a folder before anything
 * has been put in it — otherwise a new folder would vanish on the next refresh.
 */
export function CreateFolderButton({ currentPrefix, onChanged }: CreateFolderProps) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    const folder = name.trim();
    if (!folder) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fileMutate<{ success?: boolean; key?: string; error?: string }>({
        action: "createFolder",
        params: { key: `${currentPrefix}${folder}` },
      });
      if (res?.success) {
        setOpen(false);
        setName("");
        onChanged();
        notify({ tone: "success", message: t("flCreatedNotice").replace("{key}", res.key || folder) });
      } else {
        setError(res?.error || t("flNewFolderFailed"));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("flNewFolderFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fl-new-folder">
      <button className="rm-btn-sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        📁➕ {t("flNewFolder")}
      </button>
      {open && (
        <div className="fl-new-folder-panel">
          <label htmlFor="fl-folder-name">{t("flNewFolderName")}</label>
          <input
            id="fl-folder-name"
            type="text"
            value={name}
            autoFocus
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void create();
              if (e.key === "Escape") setOpen(false);
            }}
          />
          <button className="rm-btn-primary" onClick={() => void create()} disabled={busy || !name.trim()}>
            {busy ? t("loading") : t("flNewFolderCreate")}
          </button>
          {error && <div className="error-message">{error}</div>}
        </div>
      )}
    </div>
  );
}

interface CopyMoveProps {
  fileKey: string;
  fileName: string;
  /** Folder the file is in, which is what the destination box starts at. */
  currentPrefix: string;
  onChanged: () => void;
}

/**
 * Copy or move one file to another folder.
 *
 * The destination is typed rather than picked from a tree. A tree would be nicer
 * and is a larger thing to build; typing a path is bounded by the same prefix
 * boundary the backend enforces, so the worst outcome of a mistyped folder is a
 * refusal rather than a file somewhere unexpected.
 *
 * An occupied destination is refused by the backend rather than overwritten. The
 * offer to replace is made here, after the refusal, because that is the moment the
 * person knows there is something to replace.
 */
export function CopyMoveButton({ fileKey, fileName, currentPrefix, onChanged }: CopyMoveProps) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const [open, setOpen] = useState(false);
  const [destination, setDestination] = useState(currentPrefix);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Set when the backend refuses because something is already there, so the retry
  // that overwrites is a separate, deliberate click.
  const [occupied, setOccupied] = useState<"copyFile" | "moveFile" | null>(null);

  /** The key the file would land on, normalised so one trailing slash is enough. */
  const destinationKey = `${destination.replace(/\/*$/, "")}/${fileName}`.replace(/^\//, "");

  const run = async (action: "copyFile" | "moveFile", overwrite?: true) => {
    setBusy(true);
    setError(null);
    setOccupied(null);
    try {
      const res = await fileMutate<{ success?: boolean; newKey?: string; error?: string }>({
        action,
        params: overwrite
          ? { sourceKey: fileKey, destinationKey, overwrite }
          : { sourceKey: fileKey, destinationKey },
      });
      if (res?.success) {
        setOpen(false);
        onChanged();
        notify({
          tone: "success",
          message: t(action === "moveFile" ? "flMovedNotice" : "flCopiedNotice")
            .replace("{name}", fileName)
            .replace("{to}", destinationKey),
          // A move is reversible by moving back. A copy is undone by deleting the
          // copy, which is a destruction rather than a reversal, so it is not
          // offered here — the new file is visible and can be trashed.
          action:
            action === "moveFile"
              ? {
                  label: t("toastUndo"),
                  run: async () => {
                    const back = await fileMutate<{ success?: boolean; error?: string }>({
                      action: "moveFile",
                      params: { sourceKey: destinationKey, destinationKey: fileKey },
                    });
                    if (!back?.success) throw new Error(back?.error || t("flCopyMoveFailed"));
                    onChanged();
                  },
                }
              : undefined,
        });
      } else {
        setError(res?.error || t("flCopyMoveFailed"));
        if (res?.error?.includes("already exists")) setOccupied(action);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("flCopyMoveFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <span className="fl-copy-move">
      <button
        className="fl-btn"
        onClick={() => setOpen((v) => !v)}
        title={t("flCopyMove")}
        aria-label={t("flCopyMove")}
        aria-expanded={open}
      >
        📋
      </button>
      {open && (
        <div className="fl-copy-move-panel" role="dialog" aria-label={t("flCopyMove")}>
          <label htmlFor={`fl-dest-${fileKey}`}>{t("flDestination")}</label>
          <input
            id={`fl-dest-${fileKey}`}
            type="text"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            placeholder="reports/2026/"
          />
          {/* Where it lands, spelled out. A destination box on its own leaves the
              reader to work out whether the filename gets appended. */}
          <p className="rm-hint">
            {t("flDestinationHint")}: <code>{destinationKey}</code>
          </p>
          <div className="fl-copy-move-actions">
            <button className="rm-btn-sm" onClick={() => void run("copyFile")} disabled={busy}>
              {t("flCopyHere")}
            </button>
            <button className="rm-btn-primary" onClick={() => void run("moveFile")} disabled={busy}>
              {t("flMoveHere")}
            </button>
          </div>
          {/* The occupied case is recognised here, so it is worded here. Handler
              errors are English and are shown verbatim when there is nothing better
              to say; this one has a known cause and a next step, and a reader of any
              of the eight locales deserves both in their own language. */}
          {occupied ? (
            <div className="error-message">
              {t("flDestinationOccupied").replace("{key}", destinationKey)}
            </div>
          ) : (
            error && <div className="error-message">{error}</div>
          )}
          {occupied && (
            <button className="rm-btn-sm fl-replace" onClick={() => void run(occupied, true)} disabled={busy}>
              {t("flReplace")}
            </button>
          )}
        </div>
      )}
    </span>
  );
}

interface DeleteForeverProps {
  /** Key under `.trash/`; the backend refuses anything else. */
  trashKey: string;
  fileName: string;
  onChanged: () => void;
}

/**
 * Destroy a trashed object.
 *
 * The only action in the explorer with nothing behind it: the objects are not
 * versioned, so there is no earlier copy to roll back to and no undo to offer.
 * Two things stand in front of it — the backend accepts the call only for keys
 * under `.trash/`, so a file has to be trashed first, and it requires an explicit
 * acknowledgement that names the consequence.
 */
export function DeleteForeverButton({ trashKey, fileName, onChanged }: DeleteForeverProps) {
  const { t } = useTranslation();
  const { notify } = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const destroy = async () => {
    if (!window.confirm(t("flDeleteForeverConfirm").replace("{name}", fileName))) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fileMutate<{ success?: boolean; error?: string }>({
        action: "deleteFileForever",
        // Sent only from the branch behind the confirmation. The backend checks it
        // too: a dialog in a browser is a suggestion, and anything calling AppSync
        // directly never sees it.
        params: { key: trashKey, acknowledgeIrreversible: true },
      });
      if (res?.success) {
        onChanged();
        notify({ tone: "success", message: t("flDeleteForeverNotice").replace("{name}", fileName) });
      } else {
        setError(res?.error || t("flDeleteForeverFailed"));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : t("flDeleteForeverFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        className="fl-btn fl-danger"
        onClick={() => void destroy()}
        disabled={busy}
        title={t("flDeleteForever")}
        aria-label={t("flDeleteForever")}
      >
        {busy ? "…" : "🔥"}
      </button>
      {error && <span className="fl-error">{error}</span>}
    </>
  );
}
