/**
 * AgentChat — Multi-tool AI Agent with rich UI (inspired by RAG-FSxN-CDK reference).
 *
 * UI Improvements (P0-P6):
 * - P0: Markdown rendering (bold, lists, headers, code)
 * - P1: Typing animation effect on response arrival
 * - P2: Citation badges showing files the agent read
 * - P3: Feedback buttons (👍/👎) per response
 * - P4: Timeline trace with colored agent bars and duration
 * - P5: Guardrail detail (input/output assessment)
 * - P6: Response metadata (model + execution time)
 */
import { useState, useRef, useEffect, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";
import { ActionApproval, type ApprovalRequest } from "./ActionApproval";

const client = generateClient<Schema>();

function parseResponse<T>(response: { data?: string | null }): T | null {
  if (!response.data) return null;
  try {
    return typeof response.data === "string" ? JSON.parse(response.data) : response.data;
  } catch { return null; }
}

// --- Types ---

interface ToolCall {
  name: string;
  input: Record<string, unknown>;
  output?: string;
  status: "running" | "completed" | "error" | "approval_required";
  agent?: string;
}

interface AgentMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
  toolCalls?: ToolCall[];
  model?: string;
  guardrailApplied?: boolean;
  feedback?: "positive" | "negative";
  responseTimeMs?: number;
}

interface AgentResponse {
  answer: string;
  toolCalls?: ToolCall[];
  model?: string;
  error?: string;
  blocked?: boolean;
  guardrailApplied?: boolean;
  approvalRequired?: {
    actionType: string;
    target: string;
    reason: string;
    isReversible: boolean;
  };
}

// --- Agent Role Colors (from RAG reference MultiAgentTraceTimeline) ---

const AGENT_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  "file-explorer": { bg: "#ebf8ff", text: "#2b6cb0", border: "#bee3f8" },
  "safety-controller": { bg: "#fff5f5", text: "#c53030", border: "#fed7d7" },
  "general": { bg: "#f7fafc", text: "#4a5568", border: "#e2e8f0" },
};

const AGENT_ICONS: Record<string, string> = {
  "file-explorer": "📁",
  "safety-controller": "🛡️",
  "general": "⚙️",
};

// --- Suggested Prompts ---

const SUGGESTED_PROMPTS = [
  { key: "agentSuggestList", icon: "📂" },
  { key: "agentSuggestSearch", icon: "🔍" },
  { key: "agentSuggestAnalyze", icon: "📊" },
  { key: "agentSuggestRecent", icon: "🕐" },
] as const;

// --- P0: Markdown Renderer ---

function renderMarkdown(text: string): JSX.Element[] {
  const cleaned = text.replace(/<thinking>[\s\S]*?<\/thinking>/g, "").trim();
  if (!cleaned) return [];

  return cleaned.split("\n").map((line, i) => {
    const trimmed = line.trim();
    if (!trimmed) return <div key={i} className="h-1" />;

    // Headers
    if (trimmed.startsWith("### ")) return <h4 key={i} className="font-semibold text-sm mt-2 mb-1">{trimmed.slice(4)}</h4>;
    if (trimmed.startsWith("## ")) return <h3 key={i} className="font-semibold mt-2 mb-1">{trimmed.slice(3)}</h3>;

    // List items
    if (trimmed.startsWith("- ") || trimmed.startsWith("• ")) {
      return (
        <div key={i} className="flex items-start gap-1.5 ml-2">
          <span className="text-blue-500 mt-0.5">•</span>
          <span className="flex-1">{renderInline(trimmed.slice(2))}</span>
        </div>
      );
    }

    // Numbered list
    const numMatch = trimmed.match(/^(\d+)\.\s+(.+)/);
    if (numMatch) {
      return (
        <div key={i} className="flex items-start gap-1.5 ml-2">
          <span className="text-gray-500 text-xs min-w-[1.2rem]">{numMatch[1]}.</span>
          <span className="flex-1">{renderInline(numMatch[2])}</span>
        </div>
      );
    }

    // Code block marker
    if (trimmed.startsWith("```")) return null;

    // Regular paragraph
    return <p key={i} className="leading-relaxed">{renderInline(trimmed)}</p>;
  }).filter(Boolean) as JSX.Element[];
}

function renderInline(text: string): React.ReactNode {
  // Bold: **text** → <strong>
  // Code: `text` → <code>
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={i} className="bg-gray-100 px-1 rounded text-xs font-mono">{part.slice(1, -1)}</code>;
    }
    return part;
  });
}

// --- P2: Citation Extractor ---

function extractCitations(toolCalls: ToolCall[]): string[] {
  const files: string[] = [];
  for (const tc of toolCalls) {
    if (tc.name === "read_file" && tc.status === "completed" && tc.input?.key) {
      files.push(tc.input.key as string);
    }
  }
  return files;
}

// --- Component ---

export function AgentChat() {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingApproval, setPendingApproval] = useState<ApprovalRequest | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const requestStartRef = useRef<number>(0);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const generateId = () => `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  // P3: Feedback handler
  const handleFeedback = (msgId: string, rating: "positive" | "negative") => {
    setMessages((prev) =>
      prev.map((m) => (m.id === msgId ? { ...m, feedback: rating } : m))
    );
  };

  const sendMessage = useCallback(async (text?: string) => {
    const messageText = (text || input).trim();
    if (!messageText) return;

    setInput("");
    setError(null);
    requestStartRef.current = Date.now();

    const userMsg: AgentMessage = {
      id: generateId(),
      role: "user",
      content: messageText,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const history = messages.slice(-10).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const response = await (client.queries as any).agentQuery({
        action: "chat",
        params: JSON.stringify({ message: messageText, history }),
      });

      const data = parseResponse<AgentResponse>(response);
      const responseTimeMs = Date.now() - requestStartRef.current;

      if (data) {
        if (data.error) {
          setError(data.error);
          if (data.blocked) {
            setMessages((prev) => [...prev, {
              id: generateId(), role: "system",
              content: data.error || t("agentBlocked"), timestamp: Date.now(),
            }]);
          }
        } else if (data.approvalRequired) {
          setPendingApproval(data.approvalRequired);
          if (data.toolCalls && data.toolCalls.length > 0) {
            setMessages((prev) => [...prev, {
              id: generateId(), role: "assistant",
              content: t("approvalAgentWants"), timestamp: Date.now(),
              toolCalls: data.toolCalls, model: data.model, responseTimeMs,
            }]);
          }
        } else {
          setMessages((prev) => [...prev, {
            id: generateId(), role: "assistant",
            content: data.answer || "", timestamp: Date.now(),
            toolCalls: data.toolCalls, model: data.model,
            guardrailApplied: data.guardrailApplied, responseTimeMs,
          }]);
        }
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Agent request failed";
      setError(errMsg);
      setMessages((prev) => [...prev, {
        id: generateId(), role: "system",
        content: `Error: ${errMsg}`, timestamp: Date.now(),
      }]);
    } finally {
      setLoading(false);
    }
  }, [input, messages, t]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const clearHistory = () => { setMessages([]); setError(null); setPendingApproval(null); };
  const handleApprove = () => { setPendingApproval(null); setMessages((prev) => [...prev, { id: generateId(), role: "system", content: `✅ ${t("approvalApproved")}`, timestamp: Date.now() }]); };
  const handleReject = () => { setPendingApproval(null); setMessages((prev) => [...prev, { id: generateId(), role: "system", content: `❌ ${t("approvalRejected")}`, timestamp: Date.now() }]); };

  return (
    <div className="agent-chat">
      {/* Header */}
      <div className="agent-chat-header">
        <h2>🤖 {t("agentTitle")}</h2>
        {messages.length > 0 && (
          <button className="btn-sm" onClick={clearHistory} title={t("agentClear")}>🗑️</button>
        )}
      </div>

      {/* Messages */}
      <div className="agent-chat-messages" role="log" aria-label={t("agentTitle")}>
        {messages.length === 0 && !loading && (
          <div className="agent-chat-welcome">
            <div className="agent-welcome-icon">🤖</div>
            <h3>{t("agentWelcomeTitle")}</h3>
            <p>{t("agentWelcomeDesc")}</p>
            <div className="agent-suggestions">
              {SUGGESTED_PROMPTS.map((s) => (
                <button key={s.key} className="agent-suggestion-btn" onClick={() => sendMessage(t(s.key as any))}>
                  <span className="suggestion-icon">{s.icon}</span>
                  <span className="suggestion-text">{t(s.key as any)}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`agent-message agent-message-${msg.role}`}>
            {/* Header */}
            <div className="agent-message-header">
              <span className="agent-message-role">
                {msg.role === "user" ? `👤 ${t("agentYou")}` :
                 msg.role === "assistant" ? `🤖 ${t("agentAssistant")}` :
                 `⚠️ ${t("agentSystem")}`}
              </span>
              <span className="agent-message-time">
                {new Date(msg.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
            </div>

            {/* P4: Timeline Trace (colored bars per agent) */}
            {msg.toolCalls && msg.toolCalls.length > 0 && (
              <div className="agent-trace-timeline">
                <details open={msg.toolCalls.length <= 3}>
                  <summary className="trace-summary">
                    🔧 {t("agentToolCalls")} ({msg.toolCalls.length})
                    {msg.responseTimeMs && (
                      <span className="trace-duration">{(msg.responseTimeMs / 1000).toFixed(1)}s</span>
                    )}
                  </summary>
                  <div className="trace-items">
                    {msg.toolCalls.map((tc, idx) => {
                      const colors = AGENT_COLORS[tc.agent || "general"];
                      const icon = AGENT_ICONS[tc.agent || "general"];
                      return (
                        <div key={idx} className="trace-item" style={{ borderLeftColor: colors.border, background: colors.bg }}>
                          <div className="trace-item-header">
                            <span className="trace-status">
                              {tc.status === "completed" ? "✅" : tc.status === "error" ? "❌" : "⏳"}
                            </span>
                            <span className="trace-agent-badge" style={{ color: colors.text, borderColor: colors.border }}>
                              {icon} {tc.agent || "general"}
                            </span>
                            <span className="trace-tool-name">{tc.name}</span>
                          </div>
                          {tc.input && Object.keys(tc.input).length > 0 && (
                            <code className="trace-input">{JSON.stringify(tc.input).slice(0, 100)}{JSON.stringify(tc.input).length > 100 ? "…" : ""}</code>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </details>
              </div>
            )}

            {/* P0: Markdown Content */}
            <div className="agent-message-content">
              {renderMarkdown(msg.content)}
              {!msg.content.replace(/<thinking>[\s\S]*?<\/thinking>/g, "").trim() && msg.toolCalls && msg.toolCalls.length > 0 && (
                <p className="agent-processing-note">{t("agentThinking")}</p>
              )}
            </div>

            {/* P2: Citations (files the agent read) */}
            {msg.toolCalls && extractCitations(msg.toolCalls).length > 0 && (
              <div className="agent-citations">
                <span className="citation-label">📄 Sources:</span>
                {extractCitations(msg.toolCalls).map((file, i) => (
                  <span key={i} className="citation-badge" title={file}>
                    {file.split("/").pop()}
                  </span>
                ))}
              </div>
            )}

            {/* P6: Response Metadata */}
            {msg.role === "assistant" && (
              <div className="agent-response-meta">
                {msg.model && <span className="meta-model">{msg.model}</span>}
                {msg.responseTimeMs && (
                  <span className="meta-time">{(msg.responseTimeMs / 1000).toFixed(1)}s</span>
                )}
                {/* P5: Guardrail detail */}
                {msg.guardrailApplied && (
                  <span className="agent-guardrail-badge" title={t("guardrailTooltip")}>
                    🛡️ {t("guardrailApplied")}
                  </span>
                )}
              </div>
            )}

            {/* P3: Feedback Buttons */}
            {msg.role === "assistant" && !msg.feedback && (
              <div className="agent-feedback">
                <button className="feedback-btn" onClick={() => handleFeedback(msg.id, "positive")} title="Good response">👍</button>
                <button className="feedback-btn" onClick={() => handleFeedback(msg.id, "negative")} title="Bad response">👎</button>
              </div>
            )}
            {msg.feedback && (
              <div className="agent-feedback-done">
                {msg.feedback === "positive" ? "👍" : "👎"} Thanks!
              </div>
            )}
          </div>
        ))}

        {/* P1: Typing indicator with animation */}
        {loading && (
          <div className="agent-message agent-message-assistant">
            <div className="agent-message-header">
              <span className="agent-message-role">🤖 {t("agentAssistant")}</span>
            </div>
            <div className="agent-typing-indicator">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Error */}
      {error && !loading && (
        <div className="agent-chat-error">
          <span>⚠️ {error}</span>
          <button className="btn-sm" onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {/* Input */}
      <div className="agent-chat-input">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t("agentPlaceholder")}
          disabled={loading}
          rows={2}
          aria-label={t("agentInputLabel")}
        />
        <button className="agent-send-btn" onClick={() => sendMessage()} disabled={loading || !input.trim()} aria-label={t("agentSendLabel")}>
          {loading ? "⏳" : "➤"}
        </button>
      </div>

      {/* HITL */}
      {pendingApproval && (
        <ActionApproval request={pendingApproval} onApprove={handleApprove} onReject={handleReject} />
      )}
    </div>
  );
}
