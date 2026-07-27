/**
 * AgentChat — Multi-tool AI Agent embedded in the portal.
 *
 * Evolution of AiPanel: not bound to a single file, supports tool calls,
 * shows intermediate steps (search, file reads), and maintains conversation history.
 *
 * Architecture:
 *   User message → AppSync agentChat mutation
 *   → Lambda (Bedrock Converse with tool_use)
 *   → Tool loop: list_files / read_file / search_files / analyze_file
 *   → Final answer returned with tool call trace
 *
 * UX Design (per Nielsen/Krug/Cooper):
 * - Progressive disclosure: tool calls shown in collapsible <details>
 * - Visibility of system status: "Thinking...", "Reading file...", "Searching..."
 * - Goal-directed: user asks natural language, agent decides which tools to use
 * - PHI guardrail: blocks reading /dicom/, /phi/, /pii/ paths
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

// --- Suggested Prompts ---

const SUGGESTED_PROMPTS = [
  { key: "agentSuggestList", icon: "📂" },
  { key: "agentSuggestSearch", icon: "🔍" },
  { key: "agentSuggestAnalyze", icon: "📊" },
  { key: "agentSuggestRecent", icon: "🕐" },
] as const;

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

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const generateId = () => `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  const sendMessage = useCallback(async (text?: string) => {
    const messageText = (text || input).trim();
    if (!messageText) return;

    setInput("");
    setError(null);

    // Add user message
    const userMsg: AgentMessage = {
      id: generateId(),
      role: "user",
      content: messageText,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      // Build conversation history for multi-turn (last 10 messages)
      const history = messages.slice(-10).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const response = await (client.queries as any).agentQuery({
        action: "chat",
        params: JSON.stringify({
          message: messageText,
          history,
        }),
      });

      const data = parseResponse<AgentResponse>(response);

      if (data) {
        if (data.error) {
          setError(data.error);
          if (data.blocked) {
            setMessages((prev) => [
              ...prev,
              {
                id: generateId(),
                role: "system",
                content: data.error || t("agentBlocked"),
                timestamp: Date.now(),
              },
            ]);
          }
        } else if (data.approvalRequired) {
          // HITL: show approval modal
          setPendingApproval(data.approvalRequired);
          // Add trace message showing what the agent wants to do
          if (data.toolCalls && data.toolCalls.length > 0) {
            setMessages((prev) => [
              ...prev,
              {
                id: generateId(),
                role: "assistant",
                content: t("approvalAgentWants"),
                timestamp: Date.now(),
                toolCalls: data.toolCalls,
                model: data.model,
              },
            ]);
          }
        } else {
          const assistantMsg: AgentMessage = {
            id: generateId(),
            role: "assistant",
            content: data.answer || "",
            timestamp: Date.now(),
            toolCalls: data.toolCalls,
            model: data.model,
            guardrailApplied: data.guardrailApplied,
          };
          setMessages((prev) => [...prev, assistantMsg]);
        }
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Agent request failed";
      setError(errMsg);
      setMessages((prev) => [
        ...prev,
        {
          id: generateId(),
          role: "system",
          content: `Error: ${errMsg}`,
          timestamp: Date.now(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, messages, t]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearHistory = () => {
    setMessages([]);
    setError(null);
    setPendingApproval(null);
  };

  const handleApprove = () => {
    setPendingApproval(null);
    setMessages((prev) => [
      ...prev,
      {
        id: generateId(),
        role: "system",
        content: `✅ ${t("approvalApproved")}`,
        timestamp: Date.now(),
      },
    ]);
  };

  const handleReject = () => {
    setPendingApproval(null);
    setMessages((prev) => [
      ...prev,
      {
        id: generateId(),
        role: "system",
        content: `❌ ${t("approvalRejected")}`,
        timestamp: Date.now(),
      },
    ]);
  };

  return (
    <div className="agent-chat">
      {/* Header */}
      <div className="agent-chat-header">
        <h2>🤖 {t("agentTitle")}</h2>
        {messages.length > 0 && (
          <button className="btn-sm" onClick={clearHistory} title={t("agentClear")}>
            🗑️
          </button>
        )}
      </div>

      {/* Messages area */}
      <div className="agent-chat-messages" role="log" aria-label={t("agentTitle")}>
        {messages.length === 0 && !loading && (
          <div className="agent-chat-welcome">
            <div className="agent-welcome-icon">🤖</div>
            <h3>{t("agentWelcomeTitle")}</h3>
            <p>{t("agentWelcomeDesc")}</p>

            {/* Suggested prompts */}
            <div className="agent-suggestions">
              {SUGGESTED_PROMPTS.map((s) => (
                <button
                  key={s.key}
                  className="agent-suggestion-btn"
                  onClick={() => sendMessage(t(s.key as any))}
                >
                  <span className="suggestion-icon">{s.icon}</span>
                  <span className="suggestion-text">{t(s.key as any)}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`agent-message agent-message-${msg.role}`}>
            <div className="agent-message-header">
              <span className="agent-message-role">
                {msg.role === "user" ? `👤 ${t("agentYou")}` :
                 msg.role === "assistant" ? `🤖 ${t("agentAssistant")}` :
                 `⚠️ ${t("agentSystem")}`}
              </span>
              <span className="agent-message-time">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </span>
            </div>

            {/* Tool calls (progressive disclosure) */}
            {msg.toolCalls && msg.toolCalls.length > 0 && (
              <details className="agent-tool-trace">
                <summary>
                  🔧 {t("agentToolCalls")} ({msg.toolCalls.length})
                </summary>
                <div className="agent-tool-list">
                  {msg.toolCalls.map((tc, idx) => (
                    <div key={idx} className={`agent-tool-item tool-${tc.status}`}>
                      <span className="tool-icon">
                        {tc.status === "completed" ? "✅" :
                         tc.status === "error" ? "❌" :
                         tc.status === "approval_required" ? "⏳" : "⏳"}
                      </span>
                      {tc.agent && (
                        <span className="tool-agent-badge">{tc.agent}</span>
                      )}
                      <span className="tool-name">{tc.name}</span>
                      {tc.input && (
                        <code className="tool-input">
                          {JSON.stringify(tc.input).slice(0, 80)}
                          {JSON.stringify(tc.input).length > 80 ? "..." : ""}
                        </code>
                      )}
                      {tc.output && (
                        <pre className="tool-output">{tc.output.slice(0, 200)}{tc.output.length > 200 ? "..." : ""}</pre>
                      )}
                    </div>
                  ))}
                </div>
              </details>
            )}

            <div className="agent-message-content">
              {msg.content.split("\n").map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </div>

            {msg.model && (
              <span className="agent-message-model">{msg.model}</span>
            )}
            {msg.guardrailApplied && (
              <span className="agent-guardrail-badge" title={t("guardrailTooltip")}>
                🛡️ {t("guardrailApplied")}
              </span>
            )}
          </div>
        ))}

        {/* Loading indicator */}
        {loading && (
          <div className="agent-message agent-message-assistant">
            <div className="agent-message-header">
              <span className="agent-message-role">🤖 {t("agentAssistant")}</span>
            </div>
            <div className="agent-message-content agent-thinking">
              <span className="thinking-dots">{t("agentThinking")}</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Error display */}
      {error && !loading && (
        <div className="agent-chat-error">
          <span>⚠️ {error}</span>
          <button className="btn-sm" onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {/* Input area */}
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
        <button
          className="agent-send-btn"
          onClick={() => sendMessage()}
          disabled={loading || !input.trim()}
          aria-label={t("agentSendLabel")}
        >
          {loading ? "⏳" : "➤"}
        </button>
      </div>

      {/* HITL Action Approval Modal */}
      {pendingApproval && (
        <ActionApproval
          request={pendingApproval}
          onApprove={handleApprove}
          onReject={handleReject}
        />
      )}
    </div>
  );
}
