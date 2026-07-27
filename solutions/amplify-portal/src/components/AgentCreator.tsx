/**
 * AgentCreator — Form to create a custom AI agent.
 *
 * Ported from RAG-FSxN-CDK agent-creator-form pattern.
 * Fields: name, description, system prompt, tools (checkboxes), icon (emoji picker), category, shared toggle.
 */
import { useState } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

const AVAILABLE_TOOLS = [
  { id: "list_files", label: "list_files", desc: "Browse directories" },
  { id: "read_file", label: "read_file", desc: "Read file content" },
  { id: "search_files", label: "search_files", desc: "Search by name pattern" },
  { id: "get_volume_summary", label: "get_volume_summary", desc: "Volume overview" },
  { id: "kb_search", label: "kb_search", desc: "Semantic search (KB RAG)" },
  { id: "request_action_approval", label: "request_action_approval", desc: "HITL approval gate" },
];

const ICON_OPTIONS = ["🤖", "📊", "🔍", "🧠", "🛡️", "📁", "⚡", "🔬", "📋", "🎯", "💡", "🏭"];

const CATEGORY_OPTIONS = ["custom", "file-ops", "knowledge", "security", "analytics", "automation"];

interface AgentCreatorProps {
  onCreated?: (agentId: string) => void;
  onCancel?: () => void;
}

export function AgentCreator({ onCreated, onCancel }: AgentCreatorProps) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [tools, setTools] = useState<string[]>(["list_files", "read_file", "search_files"]);
  const [icon, setIcon] = useState("🤖");
  const [category, setCategory] = useState("custom");
  const [isShared, setIsShared] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleTool(toolId: string) {
    setTools((prev) =>
      prev.includes(toolId) ? prev.filter((t) => t !== toolId) : [...prev, toolId]
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) { setError(t("agentCreatorNameRequired")); return; }
    if (tools.length === 0) { setError(t("agentCreatorToolsRequired")); return; }

    setSaving(true);
    setError(null);

    try {
      const response = await (client.queries as any).agentQuery({
        action: "createAgent",
        params: JSON.stringify({
          name: name.trim(),
          description,
          systemPrompt,
          tools,
          icon,
          category,
          isShared,
        }),
      });
      const data = response.data
        ? (typeof response.data === "string" ? JSON.parse(response.data) : response.data)
        : null;
      if (data?.success && data?.agentId) {
        onCreated?.(data.agentId);
      } else if (data?.error) {
        setError(data.error);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create agent");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="agent-creator">
      <div className="agent-creator-header">
        <h2>✨ {t("agentCreatorTitle")}</h2>
        {onCancel && <button className="btn-sm" onClick={onCancel}>✕</button>}
      </div>

      {error && <div className="agent-creator-error">⚠️ {error}</div>}

      <form onSubmit={handleSubmit} className="agent-creator-form">
        {/* Icon + Name Row */}
        <div className="creator-row">
          <div className="creator-field icon-field">
            <label>{t("agentCreatorIcon")}</label>
            <div className="icon-picker">
              {ICON_OPTIONS.map((emoji) => (
                <button
                  key={emoji}
                  type="button"
                  className={`icon-option ${icon === emoji ? "selected" : ""}`}
                  onClick={() => setIcon(emoji)}
                >
                  {emoji}
                </button>
              ))}
            </div>
          </div>
          <div className="creator-field flex-1">
            <label>{t("agentCreatorName")} *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("agentCreatorNamePlaceholder")}
              maxLength={50}
            />
          </div>
        </div>

        {/* Description */}
        <div className="creator-field">
          <label>{t("agentCreatorDesc")}</label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={t("agentCreatorDescPlaceholder")}
            maxLength={200}
          />
        </div>

        {/* Category */}
        <div className="creator-field">
          <label>{t("agentCreatorCategory")}</label>
          <div className="category-selector">
            {CATEGORY_OPTIONS.map((cat) => (
              <button
                key={cat}
                type="button"
                className={`category-pill ${category === cat ? "active" : ""}`}
                onClick={() => setCategory(cat)}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* System Prompt */}
        <div className="creator-field">
          <label>{t("agentCreatorPrompt")}</label>
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder={t("agentCreatorPromptPlaceholder")}
            rows={6}
          />
          <span className="field-hint">{t("agentCreatorPromptHint")}</span>
        </div>

        {/* Tools Selection */}
        <div className="creator-field">
          <label>{t("agentCreatorTools")} *</label>
          <div className="tools-grid">
            {AVAILABLE_TOOLS.map((tool) => (
              <label key={tool.id} className={`tool-checkbox ${tools.includes(tool.id) ? "checked" : ""}`}>
                <input
                  type="checkbox"
                  checked={tools.includes(tool.id)}
                  onChange={() => toggleTool(tool.id)}
                />
                <div>
                  <span className="tool-label">{tool.label}</span>
                  <span className="tool-desc">{tool.desc}</span>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Shared Toggle */}
        <div className="creator-field">
          <label className="shared-toggle">
            <input
              type="checkbox"
              checked={isShared}
              onChange={(e) => setIsShared(e.target.checked)}
            />
            <span>{t("agentCreatorShared")}</span>
          </label>
          <span className="field-hint">{t("agentCreatorSharedHint")}</span>
        </div>

        {/* Submit */}
        <div className="creator-actions">
          {onCancel && (
            <button type="button" className="btn-secondary" onClick={onCancel}>
              {t("cancel")}
            </button>
          )}
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? "⏳" : "✨"} {t("agentCreatorSubmit")}
          </button>
        </div>
      </form>
    </div>
  );
}
