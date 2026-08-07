/**
 * AgentDirectory — Registry of custom AI agents.
 *
 * Ported from RAG-FSxN-CDK agent-directory pattern.
 * Shows a card grid of available agents with search/filter,
 * detail panel, and navigation to the agent creator.
 */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "../i18n";
import { dispatch } from "../lib/dispatch";
import { errorMessage } from "../lib/portalQuery";
import { useCurrentUserId } from "../hooks/useCurrentUserId";

interface AgentItem {
  agentId: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  tools: string[];
  isShared: boolean;
  createdBy: string;
  createdAt: number;
}

interface AgentDetail extends AgentItem {
  systemPrompt: string;
  updatedAt: number;
}

function parseResp<T>(response: { data?: unknown }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === "string" ? JSON.parse(response.data) : (response.data as T);
  } catch { return null; }
}

interface AgentDirectoryProps {
  onCreateAgent?: () => void;
  /** Open the chat running this stored agent. */
  onRunAgent?: (agentId: string, name: string) => void;
}

/** The fields `updateAgent` accepts, held while the user is editing them. */
interface EditDraft {
  name: string;
  description: string;
  systemPrompt: string;
  category: string;
  icon: string;
  isShared: boolean;
}

export function AgentDirectory({ onCreateAgent, onRunAgent }: AgentDirectoryProps) {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState("");
  const [filterCategory, setFilterCategory] = useState<string>("all");
  const [selectedAgent, setSelectedAgent] = useState<AgentDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  // Edits are drafted separately from the loaded agent so cancelling restores the
  // stored definition without another fetch.
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const currentUserId = useCurrentUserId();

  const AGENTS_KEY = ["agents", "listAgents"];

  const {
    data: agents = [],
    isPending: loading,
    error: queryError,
  } = useQuery({
    queryKey: AGENTS_KEY,
    queryFn: async () => {
      const data = parseResp<{ agents: AgentItem[] }>(
        await dispatch("agentQuery", { action: "listAgents" }),
      );
      return data?.agents ?? [];
    },
  });
  const error = errorMessage(queryError, "Failed to load agents");

  async function loadAgentDetail(agentId: string) {
    setDetailLoading(true);
    try {
      const response = await dispatch("agentQuery", {
        action: "getAgent",
        params: { agentId },
      });
      const data = parseResp<{ agent: AgentDetail }>(response);
      if (data?.agent) setSelectedAgent(data.agent);
    } catch { /* silent */ }
    finally { setDetailLoading(false); }
  }

  /**
   * Save the edited definition.
   *
   * The tool list is deliberately not editable here. Tools are chosen in the
   * creator, and the runtime intersects whatever is stored with the tools that
   * actually exist, so a list edited loosely here would not mean what it says.
   */
  async function saveEdit(agentId: string) {
    if (!editDraft) return;
    setSaving(true);
    setSaveError(null);
    try {
      const response = await dispatch("agentQuery", {
        action: "updateAgent",
        params: { agentId, ...editDraft },
      });
      const data = parseResp<{ success?: boolean; error?: string }>(response);
      if (data?.success) {
        // Reflect the edit in both the open detail panel and the card grid,
        // rather than refetching the directory to learn what was just sent.
        setSelectedAgent((prev) => (prev ? { ...prev, ...editDraft } : prev));
        queryClient.setQueryData<AgentItem[]>(AGENTS_KEY, (prev) =>
          (prev ?? []).map((a) => (a.agentId === agentId ? { ...a, ...editDraft } : a)),
        );
        setEditDraft(null);
      } else {
        setSaveError(data?.error || t("agentDirSaveFailed"));
      }
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : t("agentDirSaveFailed"));
    } finally {
      setSaving(false);
    }
  }

  async function deleteAgent(agentId: string) {
    if (!confirm(t("agentDirDeleteConfirm"))) return;
    try {
      await dispatch("agentQuery", { action: "deleteAgent", params: { agentId } });
      // Drop the row from the cache rather than refetching the whole directory.
      queryClient.setQueryData<AgentItem[]>(AGENTS_KEY, (prev) =>
        (prev ?? []).filter((a) => a.agentId !== agentId),
      );
      setSelectedAgent(null);
    } catch { /* silent */ }
  }

  // Filter + search
  const filteredAgents = agents.filter((a) => {
    if (filterCategory !== "all" && a.category !== filterCategory) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return a.name.toLowerCase().includes(q) || a.description.toLowerCase().includes(q);
    }
    return true;
  });

  const categories = ["all", ...Array.from(new Set(agents.map((a) => a.category)))];

  // Detail Panel
  if (selectedAgent) {
    return (
      <div className="agent-directory">
        <div className="agent-dir-detail">
          <button className="btn-sm" onClick={() => setSelectedAgent(null)}>← {t("agentDirBack")}</button>
          <div className="agent-dir-detail-header">
            <span className="agent-dir-detail-icon">{selectedAgent.icon}</span>
            <div>
              <h3>{selectedAgent.name}</h3>
              <span className="agent-dir-category-badge">{selectedAgent.category}</span>
              {selectedAgent.isShared && <span className="agent-dir-shared-badge">{t("agentDirShared")}</span>}
            </div>
          </div>
          <p className="agent-dir-detail-desc">{selectedAgent.description}</p>

          {detailLoading ? <p>⏳</p> : (
            <>
              <div className="agent-dir-detail-section">
                <h4>{t("agentDirTools")}</h4>
                <div className="agent-dir-tool-chips">
                  {selectedAgent.tools.map((tool) => (
                    <span key={tool} className="tool-chip">{tool}</span>
                  ))}
                </div>
              </div>

              {selectedAgent.systemPrompt && (
                <div className="agent-dir-detail-section">
                  <h4>{t("agentDirSystemPrompt")}</h4>
                  <pre className="agent-dir-prompt-preview">{selectedAgent.systemPrompt.slice(0, 500)}{selectedAgent.systemPrompt.length > 500 ? "..." : ""}</pre>
                </div>
              )}

              {editDraft && (
                <div className="agent-dir-detail-section agent-dir-edit">
                  <h4>{t("agentDirEdit")}</h4>
                  <label htmlFor="agent-edit-name">{t("agentDirFieldName")}</label>
                  <input
                    id="agent-edit-name"
                    type="text"
                    value={editDraft.name}
                    onChange={(e) => setEditDraft({ ...editDraft, name: e.target.value })}
                  />
                  <label htmlFor="agent-edit-desc">{t("agentDirFieldDescription")}</label>
                  <input
                    id="agent-edit-desc"
                    type="text"
                    value={editDraft.description}
                    onChange={(e) => setEditDraft({ ...editDraft, description: e.target.value })}
                  />
                  <label htmlFor="agent-edit-category">{t("agentDirFieldCategory")}</label>
                  <input
                    id="agent-edit-category"
                    type="text"
                    value={editDraft.category}
                    onChange={(e) => setEditDraft({ ...editDraft, category: e.target.value })}
                  />
                  <label htmlFor="agent-edit-icon">{t("agentDirFieldIcon")}</label>
                  <input
                    id="agent-edit-icon"
                    type="text"
                    maxLength={4}
                    value={editDraft.icon}
                    onChange={(e) => setEditDraft({ ...editDraft, icon: e.target.value })}
                  />
                  <label htmlFor="agent-edit-prompt">{t("agentDirFieldSystemPrompt")}</label>
                  <textarea
                    id="agent-edit-prompt"
                    rows={8}
                    value={editDraft.systemPrompt}
                    onChange={(e) => setEditDraft({ ...editDraft, systemPrompt: e.target.value })}
                  />
                  <label className="agent-dir-share-toggle">
                    <input
                      type="checkbox"
                      checked={editDraft.isShared}
                      onChange={(e) => setEditDraft({ ...editDraft, isShared: e.target.checked })}
                    />
                    {t("agentDirFieldShared")}
                  </label>
                  {/* Sharing is what lets other people run this definition, so the
                      consequence is stated next to the switch. */}
                  <p className="rm-hint">{t("agentDirSharedHint")}</p>
                  <p className="rm-hint">{t("agentDirToolsNotEditable")}</p>
                  {saveError && <div className="error-message">{saveError}</div>}
                  <div className="agent-dir-edit-actions">
                    <button
                      className="btn-primary"
                      disabled={saving || !editDraft.name.trim()}
                      onClick={() => void saveEdit(selectedAgent.agentId)}
                    >
                      {saving ? t("loading") : t("agentDirSave")}
                    </button>
                    <button
                      className="btn-sm"
                      disabled={saving}
                      onClick={() => { setEditDraft(null); setSaveError(null); }}
                    >
                      {t("flCancel")}
                    </button>
                  </div>
                </div>
              )}

              <div className="agent-dir-detail-actions">
                {onRunAgent && (
                  <button
                    className="btn-primary"
                    onClick={() => onRunAgent(selectedAgent.agentId, selectedAgent.name)}
                  >
                    💬 {t("agentDirUseInChat")}
                  </button>
                )}
                {/* Only the creator may edit or delete: the registry enforces it
                    server-side, and offering the buttons to everyone else made an
                    authorization refusal the only way to find that out. */}
                {currentUserId === selectedAgent.createdBy && (
                  <>
                    {!editDraft && (
                      <button
                        className="btn-sm"
                        onClick={() => setEditDraft({
                          name: selectedAgent.name,
                          description: selectedAgent.description,
                          systemPrompt: selectedAgent.systemPrompt ?? "",
                          category: selectedAgent.category,
                          icon: selectedAgent.icon,
                          isShared: selectedAgent.isShared,
                        })}
                      >
                        ✏️ {t("agentDirEdit")}
                      </button>
                    )}
                    <button className="btn-danger" onClick={() => deleteAgent(selectedAgent.agentId)}>
                      🗑️ {t("agentDirDelete")}
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="agent-directory">
      {/* Header */}
      <div className="agent-dir-header">
        <h2>🤖 {t("agentDirTitle")}</h2>
        {onCreateAgent && (
          <button className="btn-primary" onClick={onCreateAgent}>+ {t("agentDirCreate")}</button>
        )}
      </div>

      {/* Search + Filter */}
      <div className="agent-dir-filters">
        <input
          type="text"
          placeholder={t("agentDirSearchPlaceholder")}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="agent-dir-search"
        />
        <div className="agent-dir-category-filters">
          {categories.map((cat) => (
            <button
              key={cat}
              className={`category-pill ${filterCategory === cat ? "active" : ""}`}
              onClick={() => setFilterCategory(cat)}
            >
              {cat === "all" ? t("agentDirAll") : cat}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="agent-dir-error">⚠️ {error}</div>}

      {/* Agent Grid */}
      {loading ? (
        <div className="agent-dir-loading">⏳ {t("loading")}</div>
      ) : filteredAgents.length === 0 ? (
        <div className="agent-dir-empty">
          <p>{t("agentDirEmpty")}</p>
          {onCreateAgent && (
            <button className="btn-primary" onClick={onCreateAgent}>+ {t("agentDirCreate")}</button>
          )}
        </div>
      ) : (
        <div className="agent-dir-grid">
          {filteredAgents.map((agent) => (
            <button
              key={agent.agentId}
              className="agent-dir-card"
              onClick={() => loadAgentDetail(agent.agentId)}
            >
              <div className="agent-dir-card-header">
                <span className="agent-dir-card-icon">{agent.icon}</span>
                {agent.isShared && <span className="agent-dir-shared-dot" title={t("agentDirShared")}>●</span>}
              </div>
              <h4 className="agent-dir-card-name">{agent.name}</h4>
              <p className="agent-dir-card-desc">{agent.description.slice(0, 80)}{agent.description.length > 80 ? "..." : ""}</p>
              <div className="agent-dir-card-footer">
                <span className="agent-dir-category-badge">{agent.category}</span>
                <span className="agent-dir-tool-count">{agent.tools.length} tools</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
