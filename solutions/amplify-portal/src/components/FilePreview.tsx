import { useState, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { PdfViewer } from "./PdfViewer";
import { useTranslation } from "../i18n";

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
 * The glyph that opens a file, as a button.
 *
 * All four preview paths used `<span role="button" onClick>` with no tabIndex and no
 * key handler. `role="button"` announces a button and does nothing else: the element
 * is not focusable, so opening a file -- the thing a listing exists for -- could not
 * be reached by keyboard at all (WCAG 2.1.1, Level A). A real button brings focus,
 * Enter and Space, and the disabled and focus-visible styling with it.
 *
 * The emoji is marked decorative so a screen reader announces the label instead of
 * "page facing up".
 */
function PreviewTrigger({
  glyph,
  label,
  title,
  loading,
  onActivate,
}: {
  glyph: string;
  label: string;
  title: string;
  loading: boolean;
  onActivate: () => void;
}) {
  return (
    <button type="button" className="file-preview-btn" onClick={onActivate} title={title} aria-label={label}>
      <span aria-hidden="true">{loading ? "⏳" : glyph}</span>
    </button>
  );
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
  const { t } = useTranslation();
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
      <span className="icon file-preview-trigger">
        <PreviewTrigger
          glyph="📄"
          loading={loading}
          title={t("fpvClickDownload")}
          label={t("fpvAriaDownload").replace("{name}", fileName)}
          onActivate={() => {
            onSelect?.(fileKey, fileName);
            handleDownload();
          }}
        />
      </span>
    );
  }

  // PDF preview: use iframe with Presigned URL
  if (isPdf) {
    return (
      <span className="icon file-preview-trigger" style={{ position: "relative" }}>
        <PreviewTrigger
          glyph="📕"
          loading={loading}
          title={t("fpvClickPdf")}
          label={t("fpvAriaPdf").replace("{name}", fileName)}
          onActivate={() => {
            onSelect?.(fileKey, fileName);
            fetchPresignedUrl();
          }}
        />

        {showPreview && previewUrl && (
          <span
            className="file-preview-popover file-preview-document"
            role="dialog"
            aria-label={t("fpvAriaPdfDialog").replace("{name}", fileName)}
          >
            <PdfViewer
              url={previewUrl}
              fileName={fileName}
              onClose={() => setShowPreview(false)}
            />
          </span>
        )}
      </span>
    );
  }

  // DOCX preview: fetch and render with docx-preview
  if (isDocx) {
    return (
      <span className="icon file-preview-trigger" style={{ position: "relative" }}>
        <PreviewTrigger
          glyph="📝"
          loading={loading}
          title={t("fpvClickDoc")}
          label={t("fpvAriaDocx").replace("{name}", fileName)}
          onActivate={() => {
            onSelect?.(fileKey, fileName);
            fetchPresignedUrl();
          }}
        />

        {showPreview && previewUrl && (
          <span
            className="file-preview-popover file-preview-document"
            role="dialog"
            aria-label={t("fpvAriaDocDialog").replace("{name}", fileName)}
          >
            <span className="preview-header">
              <span className="preview-title">{fileName}</span>
              <button
                className="preview-close"
                onClick={(e) => { e.stopPropagation(); setShowPreview(false); }}
                aria-label={t("fpvClosePreview")}
              >✕</button>
            </span>
            <DocxPreviewPane url={previewUrl} />
            <span className="preview-footer">
              <button
                className="preview-download-btn"
                onClick={(e) => { e.stopPropagation(); window.open(previewUrl, "_blank"); }}
              >{t("download")}</button>
            </span>
          </span>
        )}
      </span>
    );
  }

  return (
    <span className="icon file-preview-trigger" style={{ position: "relative" }}>
      <PreviewTrigger
        glyph="🖼️"
        loading={loading}
        title={t("fpvClickPreview")}
        label={t("fpvAriaImage").replace("{name}", fileName)}
        onActivate={() => {
          onSelect?.(fileKey, fileName);
          fetchPresignedUrl();
        }}
      />

      {showPreview && previewUrl && (
        <span
          className="file-preview-popover"
          role="dialog"
          aria-label={t("fpvAriaImageDialog").replace("{name}", fileName)}
        >
          <span className="preview-header">
            <span className="preview-title">{fileName}</span>
            <button
              className="preview-close"
              onClick={(e) => {
                e.stopPropagation();
                setShowPreview(false);
              }}
              aria-label={t("fpvClosePreview")}
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
              {t("download")}
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
  const { t } = useTranslation();
  const [rendering, setRendering] = useState(false);
  const [renderError, setRenderError] = useState<string | null>(null);

  const containerCallback = useCallback((node: HTMLDivElement | null) => {
    if (!node || rendering) return;
    setRendering(true);

    // Not an async callback: React 19 lets a ref callback return a cleanup
    // function, so returning a Promise is both a type error and a promise
    // nobody observes. Start the work explicitly instead. The catch below is
    // inside the async body, so no rejection escapes.
    void (async () => {
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
    })();
  }, [url, rendering]);

  if (renderError) {
    return (
      <div className="preview-error" style={{ padding: "1rem" }}>
        <p>
          {t("fpvDocUnavailable")}: {renderError}
        </p>
        <small>{t("fpvTryDownload")}</small>
      </div>
    );
  }

  return (
    <div
      ref={containerCallback}
      className="docx-preview-container"
      style={{ maxHeight: "500px", overflow: "auto", background: "var(--color-surface)", padding: "1rem" }}
    >
      {!rendering && <p className="loading">{t("fpvLoadingDoc")}</p>}
    </div>
  );
}
