/**
 * AgentFileSidebar — Shows file path + NFS/SMB permissions for files
 * referenced in agent chat conversations.
 *
 * Ported from RAG-FSxN-CDK agent-mode-sidebar pattern.
 * Calls protectionQuery({ action: "getFilePermissions", filePath }) via existing VPC Lambda.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { errorMessage } from "../lib/portalQuery";
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
  // The explicit pick only. With none, the newest referenced file is shown, so
  // the default is derived instead of being written back into state.
  const [picked, setPicked] = useState<string>("");
  const selectedFile =
    picked || (referencedFiles.length > 0 ? referencedFiles[referencedFiles.length - 1] : "");
  const setSelectedFile = setPicked;

  // Permissions for whichever file is shown.
  //
  // The file is part of the query key, which is also what makes switching files
  // mid-flight safe: a superseded response belongs to a different key, so it can
  // no longer land last and show one file's permissions under another's name.
  // That is what the old `cancelled` flag was for.
  const {
    data: permissions = null,
    isFetching: loading,
    error: queryError,
  } = useQuery({
    queryKey: ["protection", "getFilePermissions", selectedFile],
    enabled: !!selectedFile && visible,
    queryFn: async () => {
      const response = await client.queries.protectionQuery({
        action: "getFilePermissions",
        params: JSON.stringify({ filePath: selectedFile }),
      });
      const data = response.data
        ? ((typeof response.data === "string"
            ? JSON.parse(response.data)
            : response.data) as PermissionsResponse)
        : null;
      if (data?.error) throw new Error(data.error);
      return data?.permissions ?? null;
    },
  });
  const error = errorMessage(queryError, "Failed to load permissions");

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
