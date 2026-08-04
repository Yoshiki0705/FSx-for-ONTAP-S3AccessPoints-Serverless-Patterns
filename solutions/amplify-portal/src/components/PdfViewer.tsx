import { useState } from "react";
import { useTranslation } from "../i18n";

/**
 * UX-4: PDF Inline Viewer.
 *
 * Displays PDF files inside the portal using an iframe with the Presigned URL.
 * Modern browsers have built-in PDF viewers that render inline when loaded in iframe.
 *
 * For environments where the browser PDF viewer is restricted, consider
 * adding pdf.js (pdfjs-dist) as a dependency for client-side rendering.
 *
 * Usage: <PdfViewer url={presignedUrl} fileName="contract.pdf" />
 */
export function PdfViewer({
  url,
  fileName,
  onClose,
}: {
  url: string;
  fileName?: string;
  onClose?: () => void;
}) {
  const [loading, setLoading] = useState(true);
  const { t } = useTranslation();
  const title = fileName || t("pdfTitle");

  return (
    <div className="pdf-viewer-container">
      <div className="pdf-viewer-header">
        <span className="pdf-viewer-title">{title}</span>
        <div className="pdf-viewer-actions">
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="pdf-open-btn"
            onClick={(e) => e.stopPropagation()}
          >
            {t("pdfOpenNewTab")} ↗
          </a>
          {onClose && (
            <button
              className="pdf-close-btn"
              onClick={(e) => {
                e.stopPropagation();
                onClose();
              }}
              aria-label={t("pdfClose")}
            >
              ✕ {t("pdfClose")}
            </button>
          )}
        </div>
      </div>
      {loading && <div className="pdf-loading">{t("pdfLoading")}</div>}
      <iframe
        src={url}
        className="pdf-viewer-frame"
        title={title}
        onLoad={() => setLoading(false)}
      />
    </div>
  );
}
