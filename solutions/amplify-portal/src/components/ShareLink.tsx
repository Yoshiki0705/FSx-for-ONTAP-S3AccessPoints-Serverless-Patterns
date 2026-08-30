import { useState, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

/** TTL presets in seconds, labelled through i18n */
const TTL_OPTIONS = [
  { labelKey: "slTtl5", value: 300 },
  { labelKey: "slTtl15", value: 900 },
  { labelKey: "slTtl1h", value: 3600 },
] as const;

interface ShareLinkProps {
  fileKey: string;
  fileName: string;
  /**
   * Whether this account may mint a link meant to be handed to somebody else.
   *
   * Passed in rather than read from `usePortalRole` here, because this component is
   * rendered once per row: a hook inside it would ask the same question as many times
   * as the listing is long. Required, not defaulted, so a new call site has to say
   * which answer it means instead of inheriting the permissive one.
   */
  canShareLinks: boolean;
}

/**
 * Share Link generator — creates a time-limited presigned URL and copies to clipboard.
 *
 * Uses the existing getPresignedUrl AppSync query (same Lambda backend as FilePreview).
 * The generated URL is accessible by anyone with the link until expiry — no auth required.
 *
 * Security considerations:
 * - Max TTL is 1 hour (enforced server-side in Lambda)
 * - CONFIDENTIAL files should not have share links generated (caller's responsibility)
 * - URLs are logged via CloudTrail (S3 AP GetObject data events)
 */
export function ShareLink({ fileKey, fileName, canShareLinks }: ShareLinkProps) {
  const { t } = useTranslation();
  const [showPanel, setShowPanel] = useState(false);
  const [selectedTtl, setSelectedTtl] = useState(300);
  const [generatedUrl, setGeneratedUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // A base64 PNG of the same presigned URL, for handing a link to a device that
  // cannot be typed into — a tablet on a factory floor, which is the case the
  // README has cited for "QR code access" while nothing in the UI produced one.
  const [qrCode, setQrCode] = useState<string | null>(null);
  const [qrLoading, setQrLoading] = useState(false);

  const generateLink = useCallback(async () => {
    setLoading(true);
    setError(null);
    setCopied(false);
    setGeneratedUrl(null);
    setQrCode(null);

    try {
      const response = await client.queries.getPresignedUrl({
        key: fileKey,
        expiresIn: selectedTtl,
      });

      if (response.data?.url) {
        setGeneratedUrl(response.data.url);
      } else {
        setError(response.data?.error || t("slFailed"));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("slFailed"));
    } finally {
      setLoading(false);
    }
  }, [fileKey, selectedTtl, t]);

  const copyToClipboard = useCallback(async () => {
    if (!generatedUrl) return;
    try {
      await navigator.clipboard.writeText(generatedUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for environments without clipboard API
      const textArea = document.createElement("textarea");
      textArea.value = generatedUrl;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [generatedUrl]);

  /**
   * Ask the backend for a QR code of a link with the selected expiry.
   *
   * `generateQrCode` presigns its own URL rather than encoding the one already on
   * screen, so the code and the text box are two links to the same object with the
   * same TTL, not the same link twice. Both expire.
   */
  const generateQr = useCallback(async () => {
    setQrLoading(true);
    setError(null);
    try {
      const response = await client.mutations.generateQrCode({
        key: fileKey,
        expiresIn: selectedTtl,
      });
      if (response.data?.qrCodeBase64) {
        setQrCode(response.data.qrCodeBase64);
      } else {
        setError(response.data?.error || t("slQrFailed"));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("slQrFailed"));
    } finally {
      setQrLoading(false);
    }
  }, [fileKey, selectedTtl, t]);

  const handleClose = () => {
    setShowPanel(false);
    setGeneratedUrl(null);
    setQrCode(null);
    setCopied(false);
    setError(null);
  };

  return (
    <span className="share-link-wrapper">
      <button
        className="share-link-btn"
        onClick={() => setShowPanel(!showPanel)}
        title={`${t("slShareTitle")}: ${fileName}`}
        aria-label={`${t("slGenerateAria")}: ${fileName}`}
      >
        🔗
      </button>

      {showPanel && (
        <div className="share-link-panel" role="dialog" aria-label={t("slDialogLabel")}>
          <div className="share-link-header">
            <span className="share-link-title">
              {t("slShareTitle")}: {fileName}
            </span>
            <button className="share-link-close" onClick={handleClose} aria-label={t("close")}>
              ✕
            </button>
          </div>

          <div className="share-link-ttl">
            <label>{t("slExpiresIn")}</label>
            <div className="ttl-options" role="radiogroup" aria-label={t("slExpiryGroup")}>
              {TTL_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  className={`ttl-option ${selectedTtl === opt.value ? "active" : ""}`}
                  onClick={() => {
                    setSelectedTtl(opt.value);
                    setGeneratedUrl(null);
                    setQrCode(null);
                  }}
                  role="radio"
                  aria-checked={selectedTtl === opt.value}
                >
                  {t(opt.labelKey)}
                </button>
              ))}
            </div>
          </div>

          {!generatedUrl && (
            <button
              className="share-link-generate"
              onClick={generateLink}
              disabled={loading}
            >
              {loading ? t("slGenerating") : t("slGenerate")}
            </button>
          )}

          {generatedUrl && (
            <div className="share-link-result">
              <input
                type="text"
                value={generatedUrl}
                readOnly
                className="share-link-url"
                aria-label={t("slUrlAria")}
                onClick={(e) => (e.target as HTMLInputElement).select()}
              />
              <button className="share-link-copy" onClick={copyToClipboard}>
                {copied ? t("slCopied") : t("slCopy")}
              </button>
            </div>
          )}

          {/* The QR code is refused outright for an external caller whose role does not
              allow share links -- there is no in-session use of a QR code to preserve,
              so `generateQrCode` returns a reason rather than a shortened link. The URL
              above is a different case: it is the same query the preview and the
              download button use, so the server shortens its lifetime instead. */}
          {generatedUrl && !qrCode && (canShareLinks ? (
            <button className="share-link-generate" onClick={generateQr} disabled={qrLoading}>
              {qrLoading ? t("slQrGenerating") : `📱 ${t("slQrGenerate")}`}
            </button>
          ) : (
            <p className="form-note" title={t("roleExternalShareDeniedTitle")}>
              🔒 {t("roleExternalShareDenied")}
            </p>
          ))}

          {/* Named before the link is generated, not after: the expiry buttons above
              offer lifetimes this account will not get, and finding that out from a URL
              that stopped working is the worse way to learn it. */}
          {!canShareLinks && <div className="share-link-note">{t("roleShareClampNote")}</div>}

          {qrCode && (
            <div className="share-link-qr">
              <img
                src={`data:image/png;base64,${qrCode}`}
                alt={t("slQrAlt").replace("{name}", fileName)}
              />
              <p className="form-note">{t("slQrNote")}</p>
            </div>
          )}

          {error && <div className="share-link-error" role="alert">{error}</div>}

          <div className="share-link-note">{t("slNote")}</div>
        </div>
      )}
    </span>
  );
}
