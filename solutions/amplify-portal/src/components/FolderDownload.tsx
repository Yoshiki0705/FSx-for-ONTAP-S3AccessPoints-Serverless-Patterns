import { useState } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

// Parse the JSON string response from generic dispatch endpoints
function parseResponse<T>(response: { data?: string | null }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === 'string' ? JSON.parse(response.data) : response.data;
  } catch { return null; }
}

interface FolderDownloadProps {
  currentPrefix: string;
}

interface DownloadResult {
  success: boolean;
  downloadUrl?: string;
  fileName?: string;
  fileCount?: number;
  totalBytes?: number;
  error?: string;
  demoMode?: boolean;
}

/**
 * Folder Download as ZIP — generates a ZIP archive of all files in the current folder.
 *
 * Flow:
 * 1. User clicks "Download as ZIP"
 * 2. Lambda lists all objects under prefix via S3 AP
 * 3. Lambda creates ZIP, uploads to temp bucket
 * 4. Returns a Presigned URL for the ZIP (1 hour expiry)
 *
 * Security:
 * - Requires Cognito authentication (AppSync mutation)
 * - ZIP temp bucket has 1-day lifecycle expiration
 * - Max 500 files / 500MB total per ZIP
 */
export function FolderDownload({ currentPrefix }: FolderDownloadProps) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DownloadResult | null>(null);
  const { t } = useTranslation();

  const handleDownload = async () => {
    if (!currentPrefix) return;
    setLoading(true);
    setResult(null);

    try {
      const response = await (client.mutations as any).fileMutation({
        action: "downloadFolderAsZip",
        params: JSON.stringify({ prefix: currentPrefix }),
      });

      const data = parseResponse<DownloadResult>(response);
      if (data) {
        setResult(data);
        // Auto-open download in new tab if successful
        if (data.success && data.downloadUrl) {
          window.open(data.downloadUrl, "_blank");
        }
      } else {
        setResult({ success: false, error: t("zipDownloadFailed") });
      }
    } catch (err) {
      setResult({ success: false, error: err instanceof Error ? err.message : t("zipDownloadFailed") });
    } finally {
      setLoading(false);
    }
  };

  if (!currentPrefix) return null;

  const formatBytes = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <span className="folder-download-wrapper" style={{ display: "inline-block", marginLeft: "0.5rem" }}>
      <button
        className="folder-download-btn"
        onClick={handleDownload}
        disabled={loading}
        title={t("zipDownloadTitle")}
        style={{ padding: "0.4rem 0.75rem", fontSize: "0.85rem", background: "#f1f5f9", color: "#334155", border: "1px solid #cbd5e1", borderRadius: "6px", cursor: loading ? "wait" : "pointer" }}
      >
        {loading ? `⏳ ${t("zipDownloadGenerating")}` : `📦 ${t("zipDownloadBtn")}`}
      </button>

      {result && (
        <div
          className={`folder-download-result ${result.success ? "success" : "error"}`}
          style={{
            position: "absolute",
            zIndex: 100,
            marginTop: "0.5rem",
            padding: "0.75rem",
            borderRadius: "8px",
            border: `1px solid ${result.success ? "#86efac" : "#fca5a5"}`,
            background: result.success ? "#f0fdf4" : "#fef2f2",
            fontSize: "0.85rem",
            maxWidth: "350px",
          }}
        >
          {result.success ? (
            <>
              <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>
                ✅ {t("zipDownloadReady")}
              </div>
              <div>{t("zipDownloadFileCount")}: {result.fileCount}</div>
              <div>{t("zipDownloadSize")}: {formatBytes(result.totalBytes || 0)}</div>
              {result.demoMode && (
                <div style={{ color: "#92400e", marginTop: "0.25rem" }}>⚠️ DemoMode</div>
              )}
              {result.downloadUrl && (
                <a
                  href={result.downloadUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ display: "inline-block", marginTop: "0.5rem", color: "#2563eb", textDecoration: "underline" }}
                >
                  {t("zipDownloadLink")}
                </a>
              )}
            </>
          ) : (
            <div style={{ color: "#dc2626" }}>❌ {result.error}</div>
          )}
          <button
            onClick={() => setResult(null)}
            style={{ position: "absolute", top: "0.25rem", right: "0.5rem", background: "none", border: "none", cursor: "pointer", fontSize: "1rem" }}
            aria-label={t("cancel")}
          >
            ✕
          </button>
        </div>
      )}
    </span>
  );
}
