import { useState } from "react";
import { fileMutate } from "../lib/dispatch";
import { useTranslation } from "../i18n";

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
      const res = await fileMutate<{ success?: boolean; newKey?: string; error?: string }>({
        action: "renameFile",
        params: { sourceKey: fileKey, destinationKey: `${currentPrefix}${next}` },
      });
      if (res?.success) {
        setRenaming(false);
        onChanged();
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
    if (!window.confirm(t("flTrashConfirm").replace("{name}", fileName))) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fileMutate<{ success?: boolean; error?: string }>({
        action: "trashFile",
        params: { key: fileKey },
      });
      if (res?.success) onChanged();
      else setError(res?.error || t("flTrashFailed"));
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
      if (res?.success) onChanged();
      else setError(res?.error || t("flRestoreFailed"));
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
              <p className="fl-warning">{t("flUploadLinkWarning")}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
