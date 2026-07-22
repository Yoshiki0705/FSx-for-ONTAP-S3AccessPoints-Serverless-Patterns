import { useState, useEffect, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

interface RecentFileItem {
  id: string;
  fileKey: string;
  fileName: string | null;
  accessedAt: string;
  action: string | null;
}

interface RecentFilesProps {
  onFileSelect?: (fileKey: string) => void;
}

/**
 * Recent Files component — shows files the user recently viewed or interacted with.
 *
 * Data source: DynamoDB RecentFile model (owner-scoped via Cognito).
 * Records are created by other components (FileExplorer, AiPanel) when users
 * view, download, or query files.
 *
 * Features:
 * - Sorted by most recent first
 * - Action icons (view/download/ai_query)
 * - Click to navigate back to the file
 * - Auto-cleanup of entries older than 30 days
 */
export function RecentFiles({ onFileSelect }: RecentFilesProps) {
  const [recentFiles, setRecentFiles] = useState<RecentFileItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { t } = useTranslation();

  const loadRecent = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await client.models.RecentFile.list({
        limit: 50,
      });

      if (response.data) {
        const items = (response.data as RecentFileItem[])
          .sort((a, b) => b.accessedAt.localeCompare(a.accessedAt))
          .slice(0, 30);
        setRecentFiles(items);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load recent files");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRecent();
  }, [loadRecent]);

  const getActionIcon = (action: string | null): string => {
    switch (action) {
      case "view": return "👁️";
      case "download": return "📥";
      case "ai_query": return "🤖";
      case "preview": return "🖼️";
      case "share": return "🔗";
      default: return "📄";
    }
  };

  const getActionLabel = (action: string | null): string => {
    switch (action) {
      case "view": return t("recentActionViewed");
      case "download": return t("recentActionDownloaded");
      case "ai_query": return t("recentActionAiQuery");
      case "preview": return t("recentActionPreviewed");
      case "share": return t("recentActionShared");
      default: return t("recentActionAccessed");
    }
  };

  const formatTime = (isoString: string): string => {
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMin = Math.floor(diffMs / 60000);
      const diffHour = Math.floor(diffMs / 3600000);
      const diffDay = Math.floor(diffMs / 86400000);

      if (diffMin < 1) return "just now";
      if (diffMin < 60) return `${diffMin}m ago`;
      if (diffHour < 24) return `${diffHour}h ago`;
      if (diffDay < 7) return `${diffDay}d ago`;
      return date.toLocaleDateString();
    } catch {
      return isoString;
    }
  };

  const getFileName = (item: RecentFileItem): string => {
    if (item.fileName) return item.fileName;
    const parts = item.fileKey.split("/");
    return parts[parts.length - 1] || item.fileKey;
  };

  const getFilePath = (item: RecentFileItem): string => {
    const parts = item.fileKey.split("/");
    if (parts.length <= 1) return "/";
    return parts.slice(0, -1).join("/") + "/";
  };

  if (loading) {
    return (
      <div className="recent-files">
        <h2>{t("recentTitle")}</h2>
        <p className="loading">{t("recentLoading")}</p>
      </div>
    );
  }

  return (
    <div className="recent-files">
      <div className="recent-header">
        <h2>{t("recentTitle")}</h2>
        <button onClick={loadRecent} className="refresh-btn" title={t("refresh")}>
          ↻
        </button>
      </div>

      {error && (
        <div className="info-message">
          <p>{error}</p>
        </div>
      )}

      {recentFiles.length === 0 && !error && (
        <div className="empty-state">
          <p>{t("recentEmpty")}</p>
          <small>{t("recentEmptyHint")}</small>
        </div>
      )}

      {recentFiles.length > 0 && (
        <ul className="recent-list" role="list" aria-label="Recently accessed files">
          {recentFiles.map((item) => (
            <li
              key={item.id}
              className="recent-item"
              onClick={() => onFileSelect?.(item.fileKey)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  onFileSelect?.(item.fileKey);
                }
              }}
            >
              <span className="recent-action-icon" title={getActionLabel(item.action)}>
                {getActionIcon(item.action)}
              </span>
              <div className="recent-file-info">
                <span className="recent-file-name">{getFileName(item)}</span>
                <span className="recent-file-path">{getFilePath(item)}</span>
              </div>
              <div className="recent-meta">
                <span className="recent-action-label">{getActionLabel(item.action)}</span>
                <span className="recent-time">{formatTime(item.accessedAt)}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Utility function to record a file access event.
 * Call this from FileExplorer, AiPanel, or any component that accesses files.
 */
export async function recordRecentFile(
  fileKey: string,
  action: "view" | "download" | "ai_query" | "preview" | "share" = "view",
  fileName?: string
): Promise<void> {
  try {
    await client.models.RecentFile.create({
      fileKey,
      fileName: fileName || fileKey.split("/").pop() || fileKey,
      accessedAt: new Date().toISOString(),
      action,
    });
  } catch (err) {
    // Non-critical — don't block the user's action if logging fails
    console.warn("Failed to record recent file:", err);
  }
}
