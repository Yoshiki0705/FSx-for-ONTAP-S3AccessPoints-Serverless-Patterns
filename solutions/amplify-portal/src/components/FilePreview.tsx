import { useState } from "react";

const IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"];

interface FilePreviewProps {
  fileKey: string;
  fileName: string;
}

/**
 * Inline file preview for image files.
 *
 * Shows a thumbnail icon (🖼️) that expands to show a preview tooltip on hover.
 * For non-image files, shows the standard document icon (📄).
 *
 * Note: Actual image loading requires a presigned URL or proxy endpoint.
 * This component currently shows a placeholder preview indicator.
 * In production, connect to a GetObject presigned URL or AppSync query.
 */
export function FilePreview({ fileKey: _fileKey, fileName }: FilePreviewProps) {
  const [showPreview, setShowPreview] = useState(false);

  const extension = fileName.toLowerCase().slice(fileName.lastIndexOf("."));
  const isImage = IMAGE_EXTENSIONS.includes(extension);

  if (!isImage) {
    return <span className="icon">📄</span>;
  }

  return (
    <span
      className="icon file-preview-trigger"
      onMouseEnter={() => setShowPreview(true)}
      onMouseLeave={() => setShowPreview(false)}
      aria-label={`Image file: ${fileName}`}
    >
      🖼️
      {showPreview && (
        <span className="file-preview-tooltip" role="tooltip">
          <span className="preview-placeholder">
            Preview: {fileName}
          </span>
          <small className="preview-hint">
            {extension.toUpperCase().replace(".", "")} image
          </small>
        </span>
      )}
    </span>
  );
}
