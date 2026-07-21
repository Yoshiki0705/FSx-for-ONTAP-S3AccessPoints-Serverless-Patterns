import { useState, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";

const client = generateClient<Schema>();

const IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"];
const PDF_EXTENSIONS = [".pdf"];
const DOCX_EXTENSIONS = [".docx"];
const PREVIEWABLE_EXTENSIONS = [...IMAGE_EXTENSIONS, ...PDF_EXTENSIONS, ...DOCX_EXTENSIONS];

interface BoundingBox {
  width: number;
  height: number;
  left: number;
  top: number;
}

interface LabelInstance {
  boundingBox: BoundingBox;
  confidence: number;
}

interface DetectedLabel {
  name: string;
  confidence: number;
  instances: LabelInstance[];
}

interface FilePreviewProps {
  fileKey: string;
  fileName: string;
  onSelect?: (fileKey: string, fileName: string) => void;
}

/**
 * Inline file preview with presigned URL image loading.
 *
 * For image files: shows 🖼️ icon. On click, fetches a presigned URL
 * from the getPresignedUrl AppSync query and displays the actual image
 * in a popover. Presigned URLs are time-limited (5 min default).
 *
 * For non-image files: shows 📄 icon with download-on-click.
 *
 * Architecture:
 *   Click → AppSync getPresignedUrl → Lambda → boto3 generate_presigned_url
 *   → S3 AP alias (FSx for ONTAP) → signed URL → <img src={url} />
 */
export function FilePreview({ fileKey, fileName, onSelect }: FilePreviewProps) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [labels, setLabels] = useState<DetectedLabel[]>([]);
  const [labelsLoading, setLabelsLoading] = useState(false);

  const extension = fileName.toLowerCase().slice(fileName.lastIndexOf("."));
  const isPdf = PDF_EXTENSIONS.includes(extension);
  const isDocx = DOCX_EXTENSIONS.includes(extension);
  const isPreviewable = PREVIEWABLE_EXTENSIONS.includes(extension);

  const fetchPresignedUrl = useCallback(async () => {
    if (previewUrl) {
      // Already fetched, just show
      setShowPreview(true);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await client.queries.getPresignedUrl({
        key: fileKey,
        expiresIn: 300, // 5 minutes
      });

      if (response.data?.url) {
        setPreviewUrl(response.data.url);
        setShowPreview(true);
      } else {
        setError(response.data?.error || "Failed to generate preview URL");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preview unavailable");
    } finally {
      setLoading(false);
    }
  }, [fileKey, previewUrl]);

  const handleDownload = useCallback(async () => {
    setLoading(true);
    try {
      const response = await client.queries.getPresignedUrl({
        key: fileKey,
        expiresIn: 60,
      });
      if (response.data?.url) {
        window.open(response.data.url, "_blank");
      }
    } catch (err) {
      console.error("Download failed:", err);
    } finally {
      setLoading(false);
    }
  }, [fileKey]);

  const handleDetectLabels = useCallback(async () => {
    if (labels.length > 0) return; // Already detected
    setLabelsLoading(true);
    try {
      const response = await client.mutations.detectLabels({
        key: fileKey,
        maxLabels: 10,
        minConfidence: 70,
      });
      if (response.data?.labels) {
        setLabels(response.data.labels as DetectedLabel[]);
      }
    } catch (err) {
      console.error("Label detection failed:", err);
    } finally {
      setLabelsLoading(false);
    }
  }, [fileKey, labels.length]);

  if (!isPreviewable) {
    return (
      <span
        className="icon file-preview-trigger"
        onClick={() => {
          onSelect?.(fileKey, fileName);
          handleDownload();
        }}
        title="Click to download / select for AI"
        role="button"
        aria-label={`Download ${fileName}`}
      >
        {loading ? "⏳" : "📄"}
      </span>
    );
  }

  // PDF preview: use iframe with Presigned URL
  if (isPdf) {
    return (
      <span className="icon file-preview-trigger" style={{ position: "relative" }}>
        <span
          onClick={() => {
            onSelect?.(fileKey, fileName);
            fetchPresignedUrl();
          }}
          role="button"
          aria-label={`Preview PDF: ${fileName}`}
          title="Click to preview PDF"
          style={{ cursor: "pointer" }}
        >
          {loading ? "⏳" : "📕"}
        </span>

        {showPreview && previewUrl && (
          <span
            className="file-preview-popover file-preview-document"
            role="dialog"
            aria-label={`PDF preview: ${fileName}`}
          >
            <span className="preview-header">
              <span className="preview-title">{fileName}</span>
              <button
                className="preview-close"
                onClick={(e) => { e.stopPropagation(); setShowPreview(false); }}
                aria-label="Close preview"
              >✕</button>
            </span>
            <iframe
              src={previewUrl}
              title={`PDF preview: ${fileName}`}
              className="preview-pdf-iframe"
              style={{ width: "100%", height: "500px", border: "none" }}
            />
            <span className="preview-footer">
              <button
                className="preview-download-btn"
                onClick={(e) => { e.stopPropagation(); window.open(previewUrl, "_blank"); }}
              >Open in new tab</button>
            </span>
          </span>
        )}
      </span>
    );
  }

  // DOCX preview: fetch and render with docx-preview
  if (isDocx) {
    return (
      <span className="icon file-preview-trigger" style={{ position: "relative" }}>
        <span
          onClick={() => {
            onSelect?.(fileKey, fileName);
            fetchPresignedUrl();
          }}
          role="button"
          aria-label={`Preview DOCX: ${fileName}`}
          title="Click to preview document"
          style={{ cursor: "pointer" }}
        >
          {loading ? "⏳" : "📝"}
        </span>

        {showPreview && previewUrl && (
          <span
            className="file-preview-popover file-preview-document"
            role="dialog"
            aria-label={`Document preview: ${fileName}`}
          >
            <span className="preview-header">
              <span className="preview-title">{fileName}</span>
              <button
                className="preview-close"
                onClick={(e) => { e.stopPropagation(); setShowPreview(false); }}
                aria-label="Close preview"
              >✕</button>
            </span>
            <DocxPreviewPane url={previewUrl} />
            <span className="preview-footer">
              <button
                className="preview-download-btn"
                onClick={(e) => { e.stopPropagation(); window.open(previewUrl, "_blank"); }}
              >Download</button>
            </span>
          </span>
        )}
      </span>
    );
  }

  return (
    <span className="icon file-preview-trigger" style={{ position: "relative" }}>
      <span
        onClick={() => {
          onSelect?.(fileKey, fileName);
          fetchPresignedUrl();
        }}
        role="button"
        aria-label={`Preview ${fileName}`}
        title="Click to preview"
        style={{ cursor: "pointer" }}
      >
        {loading ? "⏳" : "🖼️"}
      </span>

      {showPreview && previewUrl && (
        <span
          className="file-preview-popover"
          role="dialog"
          aria-label={`Image preview: ${fileName}`}
        >
          <span className="preview-header">
            <span className="preview-title">{fileName}</span>
            <button
              className="preview-close"
              onClick={(e) => {
                e.stopPropagation();
                setShowPreview(false);
              }}
              aria-label="Close preview"
            >
              ✕
            </button>
          </span>
          <img
            src={previewUrl}
            alt={fileName}
            className="preview-image"
            onError={() => setError("Failed to load image")}
          />
          <span className="preview-footer">
            <button
              className="preview-download-btn"
              onClick={(e) => {
                e.stopPropagation();
                window.open(previewUrl, "_blank");
              }}
            >
              Download
            </button>
            <button
              className="preview-detect-btn"
              onClick={(e) => {
                e.stopPropagation();
                handleDetectLabels();
              }}
              disabled={labelsLoading}
            >
              {labelsLoading ? "Detecting..." : labels.length > 0 ? `${labels.length} labels` : "Detect Objects"}
            </button>
          </span>
          {labels.length > 0 && (
            <span className="preview-labels">
              {labels.map((label, idx) => (
                <span key={idx} className="preview-label-tag">
                  {label.name} ({label.confidence}%)
                </span>
              ))}
            </span>
          )}
        </span>
      )}

      {showPreview && error && (
        <span className="file-preview-tooltip" role="alert">
          <span className="preview-error">{error}</span>
        </span>
      )}
    </span>
  );
}


/**
 * DOCX Preview Pane — renders a .docx file in the browser using docx-preview.
 * Fetches the file via Presigned URL and renders it into a container div.
 */
function DocxPreviewPane({ url }: { url: string }) {
  const [rendering, setRendering] = useState(false);
  const [renderError, setRenderError] = useState<string | null>(null);

  const containerCallback = useCallback(async (node: HTMLDivElement | null) => {
    if (!node || rendering) return;
    setRendering(true);

    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`Fetch failed: ${response.status}`);
      const blob = await response.blob();

      // Dynamic import to avoid bundling docx-preview when unused
      const { renderAsync } = await import("docx-preview");
      await renderAsync(blob, node, undefined, {
        className: "docx-preview-content",
        inWrapper: true,
      });
    } catch (err) {
      setRenderError(err instanceof Error ? err.message : "Failed to render document");
    }
  }, [url, rendering]);

  if (renderError) {
    return (
      <div className="preview-error" style={{ padding: "1rem" }}>
        <p>Document preview unavailable: {renderError}</p>
        <small>Try downloading the file instead.</small>
      </div>
    );
  }

  return (
    <div
      ref={containerCallback}
      className="docx-preview-container"
      style={{ maxHeight: "500px", overflow: "auto", background: "white", padding: "1rem" }}
    >
      {!rendering && <p className="loading">Loading document preview...</p>}
    </div>
  );
}
