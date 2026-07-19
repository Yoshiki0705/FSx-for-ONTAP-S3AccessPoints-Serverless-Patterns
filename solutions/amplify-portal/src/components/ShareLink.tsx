import { useState, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";

const client = generateClient<Schema>();

/** TTL presets in seconds */
const TTL_OPTIONS = [
  { label: "5 min", value: 300 },
  { label: "15 min", value: 900 },
  { label: "1 hour", value: 3600 },
] as const;

interface ShareLinkProps {
  fileKey: string;
  fileName: string;
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
export function ShareLink({ fileKey, fileName }: ShareLinkProps) {
  const [showPanel, setShowPanel] = useState(false);
  const [selectedTtl, setSelectedTtl] = useState(300);
  const [generatedUrl, setGeneratedUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generateLink = useCallback(async () => {
    setLoading(true);
    setError(null);
    setCopied(false);
    setGeneratedUrl(null);

    try {
      const response = await client.queries.getPresignedUrl({
        key: fileKey,
        expiresIn: selectedTtl,
      });

      if (response.data?.url) {
        setGeneratedUrl(response.data.url);
      } else {
        setError(response.data?.error || "Failed to generate link");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Link generation failed");
    } finally {
      setLoading(false);
    }
  }, [fileKey, selectedTtl]);

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

  const handleClose = () => {
    setShowPanel(false);
    setGeneratedUrl(null);
    setCopied(false);
    setError(null);
  };

  return (
    <span className="share-link-wrapper">
      <button
        className="share-link-btn"
        onClick={() => setShowPanel(!showPanel)}
        title={`Share ${fileName}`}
        aria-label={`Generate share link for ${fileName}`}
      >
        🔗
      </button>

      {showPanel && (
        <div className="share-link-panel" role="dialog" aria-label="Share link">
          <div className="share-link-header">
            <span className="share-link-title">Share: {fileName}</span>
            <button className="share-link-close" onClick={handleClose} aria-label="Close">
              ✕
            </button>
          </div>

          <div className="share-link-ttl">
            <label>Expires in:</label>
            <div className="ttl-options" role="radiogroup" aria-label="Link expiry time">
              {TTL_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  className={`ttl-option ${selectedTtl === opt.value ? "active" : ""}`}
                  onClick={() => {
                    setSelectedTtl(opt.value);
                    setGeneratedUrl(null);
                  }}
                  role="radio"
                  aria-checked={selectedTtl === opt.value}
                >
                  {opt.label}
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
              {loading ? "Generating..." : "Generate Link"}
            </button>
          )}

          {generatedUrl && (
            <div className="share-link-result">
              <input
                type="text"
                value={generatedUrl}
                readOnly
                className="share-link-url"
                aria-label="Generated share link URL"
                onClick={(e) => (e.target as HTMLInputElement).select()}
              />
              <button className="share-link-copy" onClick={copyToClipboard}>
                {copied ? "✓ Copied" : "Copy"}
              </button>
            </div>
          )}

          {error && <div className="share-link-error" role="alert">{error}</div>}

          <div className="share-link-note">
            Anyone with this link can access the file until it expires. Do not share links to confidential files.
          </div>
        </div>
      )}
    </span>
  );
}
