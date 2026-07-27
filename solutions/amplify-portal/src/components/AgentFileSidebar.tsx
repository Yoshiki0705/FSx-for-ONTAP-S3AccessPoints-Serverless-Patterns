/**
 * AgentFileSidebar — Shows file path + NFS/SMB permissions for files
 * referenced in agent chat conversations.
 *
 * Ported from RAG-FSxN-CDK agent-mode-sidebar pattern.
 * Calls protectionQuery({ action: "getFilePermissions", filePath }) via existing VPC Lambda.
 */
import { useState, useEffect } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

interface FilePermissions {
  securityStyle: string;
  owner: string;
  group: string;
  unixPermissions: string;
  acls: Array<{
    user: string;
    access: string;
    accessControl: string;
    applyTo: Record<string, boolean>;
  }>;
}

interface PermissionsResponse {
  filePath: string;
  permissions: FilePermissions | null;
  error: string | null;
}

interface AgentFileSidebarProps {
  /** File paths referenced in the current conversation (from tool traces) */
  referencedFiles: string[];
  /** Whether the sidebar is visible */
  visible: boolean;
  onClose: () => void;
}

export function AgentFileSidebar({ referencedFiles, visible, onClose }: AgentFileSidebarProps) {
  const { t } = useTranslation();
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [permissions, setPermissions] = useState<FilePermissions | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Auto-select latest file
  useEffect(() => {
    if (referencedFiles.length > 0 && !selectedFile) {
      setSelectedFile(referencedFiles[referencedFiles.length - 1]);
    }
  }, [referencedFiles, selectedFile]);

  // Fetch permissions when file changes
  useEffect(() => {
    if (!selectedFile || !visible) return;
    fetchPermissions(selectedFile);
  }, [selectedFile, visible]);

  async function fetchPermissions(filePath: string) {
    setLoading(true);
    setError(null);
    setPermissions(null);

    try {
      const response = await client.queries.protectionQuery({
        action: "getFilePermissions",
        params: JSON.stringify({ filePath }),
      });
      const data = response.data
        ? (typeof response.data === "string" ? JSON.parse(response.data) : response.data) as PermissionsResponse
        : null;

      if (data?.permissions) {
        setPermissions(data.permissions);
      }
      if (data?.error) {
        setError(data.error);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load permissions");
    } finally {
      setLoading(false);
    }
  }

  if (!visible || referencedFiles.length === 0) return null;

  return (
    <div className="agent-file-sidebar">
      <div className="afs-header">
        <h4>📂 {t("sidebarFileInfo")}</h4>
        <button className="btn-sm" onClick={onClose}>✕</button>
      </div>

      {/* File List */}
      <div className="afs-file-list">
        {referencedFiles.map((file) => (
          <button
            key={file}
            className={`afs-file-item ${file === selectedFile ? "active" : ""}`}
            onClick={() => setSelectedFile(file)}
          >
            <span className="afs-file-icon">📄</span>
            <span className="afs-file-name">{file.split("/").pop()}</span>
          </button>
        ))}
      </div>

      {/* Selected File Details */}
      {selectedFile && (
        <div className="afs-details">
          <div className="afs-path">
            <span className="afs-label">{t("sidebarPath")}</span>
            <code className="afs-path-value">{selectedFile}</code>
          </div>

          {loading && <div className="afs-loading">⏳ {t("sidebarLoadingPerms")}</div>}

          {error && <div className="afs-error">⚠️ {error}</div>}

          {permissions && (
            <div className="afs-permissions">
              <div className="afs-perm-row">
                <span className="afs-label">{t("sidebarSecurityStyle")}</span>
                <span className="afs-badge">{permissions.securityStyle || "unix"}</span>
              </div>
              <div className="afs-perm-row">
                <span className="afs-label">{t("sidebarOwner")}</span>
                <span>{permissions.owner || "—"}</span>
              </div>
              <div className="afs-perm-row">
                <span className="afs-label">{t("sidebarGroup")}</span>
                <span>{permissions.group || "—"}</span>
              </div>
              {permissions.unixPermissions && (
                <div className="afs-perm-row">
                  <span className="afs-label">{t("sidebarUnixPerms")}</span>
                  <code>{permissions.unixPermissions}</code>
                </div>
              )}
              {permissions.acls.length > 0 && (
                <div className="afs-acls">
                  <span className="afs-label">{t("sidebarAcls")}</span>
                  <table className="afs-acl-table">
                    <thead>
                      <tr>
                        <th>{t("sidebarUser")}</th>
                        <th>{t("sidebarAccess")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {permissions.acls.map((acl, i) => (
                        <tr key={i}>
                          <td>{acl.user}</td>
                          <td><span className={`afs-access-badge ${acl.access}`}>{acl.access}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
