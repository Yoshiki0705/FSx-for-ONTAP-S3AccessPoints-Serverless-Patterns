/**
 * AgentCreator — Form to create a custom AI agent.
 *
 * Ported from RAG-FSxN-CDK agent-creator-form pattern.
 * Fields: name, description, system prompt, tools (checkboxes), icon (icon picker), category, shared toggle.
 */
import { useState } from "react";
import { useTranslation } from "../i18n";
import { dispatch } from "../lib/dispatch";
import { Icon } from "./Icon";
import { AGENT_ICON_CHOICES } from "./AgentIcon";
import { AGENT_INDUSTRY_TEMPLATES, buildSystemPrompt } from "../lib/agentIndustryTemplates";

const AVAILABLE_TOOLS = [
  { id: "list_files", label: "list_files", desc: "Browse directories" },
  { id: "read_file", label: "read_file", desc: "Read file content" },
  { id: "search_files", label: "search_files", desc: "Search by name pattern" },
  { id: "get_volume_summary", label: "get_volume_summary", desc: "Volume overview" },
  { id: "kb_search", label: "kb_search", desc: "Semantic search (KB RAG)" },
  { id: "request_action_approval", label: "request_action_approval", desc: "HITL approval gate" },
];


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
  const [icon, setIcon] = useState("bot");
  const [category, setCategory] = useState("custom");
  const [isShared, setIsShared] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fills the form from an industry template. Every field stays editable.
  function applyTemplate(templateId: string) {
    const template = AGENT_INDUSTRY_TEMPLATES.find((item) => item.id === templateId);
    if (!template) return;
    setName(t(template.nameKey));
    setDescription(t(template.descKey));
    setSystemPrompt(buildSystemPrompt(template));
    setTools(template.tools);
    setCategory(template.category);
    if ((AGENT_ICON_CHOICES as string[]).includes(template.icon)) setIcon(template.icon);
  }
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
      const response = await dispatch("agentQuery", {
        action: "createAgent",
        params: {
          name: name.trim(),
          description,
          systemPrompt,
          tools,
          icon,
          category,
          isShared,
        },
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
        <h2><Icon name="sparkles" className="icon-lead" />{t("agentCreatorTitle")}</h2>
        {onCancel && <button className="btn-sm" onClick={onCancel} aria-label={t("close")}><Icon name="close" /></button>}
      </div>

      {error && <div className="agent-creator-error"><Icon name="alert-triangle" className="icon-lead" />{error}</div>}

      <form onSubmit={handleSubmit} className="agent-creator-form">
        {/* Industry template */}
        <div className="creator-field">
          <label htmlFor="agent-template">{t("agentCreatorTemplate")}</label>
          <select
            id="agent-template"
            defaultValue=""
            onChange={(e) => applyTemplate(e.target.value)}
          >
            <option value="">{t("agentCreatorTemplateNone")}</option>
            {AGENT_INDUSTRY_TEMPLATES.map((template) => (
              <option key={template.id} value={template.id}>
                {t(template.nameKey)}
              </option>
            ))}
          </select>
          <span className="field-hint">{t("agentCreatorTemplateHint")}</span>
        </div>
        {/* Icon + Name Row */}
        <div className="creator-row">
          <div className="creator-field icon-field">
            <label>{t("agentCreatorIcon")}</label>
            <div className="icon-picker">
              {AGENT_ICON_CHOICES.map((choice) => (
                <button
                  key={choice}
                  type="button"
                  className={`icon-option ${icon === choice ? "selected" : ""}`}
                  onClick={() => setIcon(choice)}
                  aria-label={choice}
                >
                  <Icon name={choice} />
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
            <Icon name={saving ? "hourglass" : "sparkles"} className="icon-lead" />{t("agentCreatorSubmit")}
          </button>
        </div>
      </form>
    </div>
  );
}
