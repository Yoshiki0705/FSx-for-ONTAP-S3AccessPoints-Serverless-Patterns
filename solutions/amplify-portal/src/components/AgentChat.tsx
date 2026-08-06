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
// React 19 removed the global `JSX` namespace; it is now exported from "react".
import type { JSX } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation, type TranslationKeys } from "../i18n";
import { ActionApproval, type ApprovalRequest } from "./ActionApproval";
import { AgentFileSidebar } from "./AgentFileSidebar";
import { parseResponse } from "../utils/parseResponse";

const client = generateClient<Schema>();

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
  "knowledge-analyst": { bg: "#faf5ff", text: "#6b46c1", border: "#e9d8fd" },
  "safety-controller": { bg: "#fff5f5", text: "#c53030", border: "#fed7d7" },
  "general": { bg: "#f7fafc", text: "#4a5568", border: "#e2e8f0" },
};

const AGENT_ICONS: Record<string, string> = {
  "file-explorer": "📁",
  "knowledge-analyst": "🧠",
  "safety-controller": "🛡️",
  "general": "⚙️",
};

// --- Suggested Prompts (Card Grid) ---

interface TaskCard {
  id: string;
  icon: string;
  // Typed as TranslationKeys, not string, so a key that no locale defines is a
  // compile error here rather than a card rendering its own key name at runtime.
  // These were `string`, which forced `t(card.titleKey as any)` at each use.
  titleKey: TranslationKeys;
  descKey: TranslationKeys;
  promptKey: TranslationKeys;
  agent: string;
  color: string;
}

const TASK_CARDS: TaskCard[] = [
  {
    id: "browse",
    icon: "📂",
    titleKey: "cardBrowseTitle",
    descKey: "cardBrowseDesc",
    promptKey: "agentSuggestList",
    agent: "file-explorer",
    color: "#ebf8ff",
  },
  {
    id: "search",
    icon: "🔍",
    titleKey: "cardSearchTitle",
    descKey: "cardSearchDesc",
    promptKey: "agentSuggestSearch",
    agent: "file-explorer",
    color: "#f0fff4",
  },
  {
    id: "knowledge",
    icon: "🧠",
    titleKey: "cardKnowledgeTitle",
    descKey: "cardKnowledgeDesc",
    promptKey: "cardKnowledgePrompt",
    agent: "knowledge-analyst",
    color: "#faf5ff",
  },
  {
    id: "analyze",
    icon: "📊",
    titleKey: "cardAnalyzeTitle",
    descKey: "cardAnalyzeDesc",
    promptKey: "agentSuggestAnalyze",
    agent: "knowledge-analyst",
    color: "#fffbeb",
  },
  {
    id: "protect",
    icon: "🛡️",
    titleKey: "cardProtectTitle",
    descKey: "cardProtectDesc",
    promptKey: "cardProtectPrompt",
    agent: "safety-controller",
    color: "#fff5f5",
  },
  {
    id: "recent",
    icon: "🕐",
    titleKey: "cardRecentTitle",
    descKey: "cardRecentDesc",
    promptKey: "agentSuggestRecent",
    agent: "file-explorer",
    color: "#f7fafc",
  },
];

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

interface ChatSession {
  sessionId: string;
  title: string;
  messageCount: number;
  createdAt: number;
  updatedAt: number;
}

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

  // --- Chat History State ---
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string>("");
  const [showHistory, setShowHistory] = useState(false);
  const [showFileSidebar, setShowFileSidebar] = useState(false);
  const [attachedImage, setAttachedImage] = useState<{ data: string; mediaType: string; preview: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [agentMode, setAgentMode] = useState<"multi" | "kb" | "agent">("multi");

  // Extract referenced files from tool traces
  const referencedFiles = messages
    .flatMap((m) => m.toolCalls || [])
    .filter((tc) => tc.name === "read_file" || tc.name === "list_files")
    .map((tc) => {
      if (tc.name === "read_file") return (tc.input as { key?: string }).key || "";
      if (tc.name === "list_files") return (tc.input as { prefix?: string }).prefix || "/";
      return "";
    })
    .filter((f) => f && f !== "/")
    .filter((f, i, arr) => arr.indexOf(f) === i); // deduplicate

  // loadSessions and saveCurrentSession are useCallback rather than plain function
  // declarations, and are declared above the effects that use them.
  //
  // As function declarations they were re-created every render, so the auto-save
  // effect could not list saveCurrentSession as a dependency. It was not actually
  // reading stale values — the effect re-runs on messages and currentSessionId, so
  // the closure it captured came from the same render as those values. But adding
  // the function to satisfy the linter would have re-run the effect on *every*
  // render, clearing and restarting the 2-second timer each time and starving the
  // debounce it exists to provide.
  //
  // Memoising instead makes the identity change exactly when messages or
  // currentSessionId change, which is what the dependency array already said.
  const loadSessions = useCallback(async () => {
    try {
      const response = await client.queries.agentQuery({
        action: "listSessions",
        params: JSON.stringify({ limit: 20 }),
      });
      const data = parseResponse<{ sessions: ChatSession[] }>(response);
      if (data?.sessions) setSessions(data.sessions);
    } catch { /* silent */ }
  }, []);

  const saveCurrentSession = useCallback(async () => {
    if (messages.length === 0) return;
    const title = messages[0]?.content.slice(0, 50) || "Untitled";
    const sessionId = currentSessionId || `sess-${Date.now()}`;
    if (!currentSessionId) setCurrentSessionId(sessionId);

    try {
      await client.queries.agentQuery({
        action: "saveSession",
        params: JSON.stringify({
          sessionId,
          title,
          messages: messages.map((m) => ({ role: m.role, content: m.content, timestamp: m.timestamp })),
          createdAt: messages[0]?.timestamp || Date.now(),
        }),
      });
      loadSessions();
    } catch { /* silent fail */ }
  }, [messages, currentSessionId, loadSessions]);

  // Load session list on mount
  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Auto-save after messages change (debounced)
  // React 19 requires useRef to be called with an explicit initial value.
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => {
    if (messages.length === 0 || !currentSessionId) return;
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(() => {
      saveCurrentSession();
    }, 2000);
    return () => { if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current); };
  }, [messages, currentSessionId, saveCurrentSession]);

  async function loadSession(sessionId: string) {
    try {
      const response = await client.queries.agentQuery({
        action: "loadSession",
        params: JSON.stringify({ sessionId }),
      });
      const data = parseResponse<{ messages: Array<{ role: string; content: string; timestamp: number }> }>(response);
      if (data?.messages) {
        setMessages(data.messages.map((m) => ({
          id: `msg-${m.timestamp}-${Math.random().toString(36).slice(2, 8)}`,
          role: m.role as "user" | "assistant" | "system",
          content: m.content,
          timestamp: m.timestamp,
        })));
        setCurrentSessionId(sessionId);
        setShowHistory(false);
      }
    } catch { /* silent */ }
  }

  async function deleteSession(sessionId: string) {
    try {
      await client.queries.agentQuery({
        action: "deleteSession",
        params: JSON.stringify({ sessionId }),
      });
      setSessions((prev) => prev.filter((s) => s.sessionId !== sessionId));
      if (currentSessionId === sessionId) {
        setMessages([]);
        setCurrentSessionId("");
      }
    } catch { /* silent */ }
  }

  // --- Image Upload Handlers ---
  function handleImageSelect(file: File) {
    if (!file.type.startsWith("image/")) return;
    if (file.size > 5 * 1024 * 1024) { setError("Image must be under 5MB"); return; }

    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target?.result as string;
      const base64 = dataUrl.split(",")[1];
      setAttachedImage({ data: base64, mediaType: file.type, preview: dataUrl });
    };
    reader.readAsDataURL(file);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleImageSelect(file);
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleImageSelect(file);
    e.target.value = "";
  }

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

      const chatParams: Record<string, unknown> = { message: messageText, history, mode: agentMode };
      if (attachedImage) {
        chatParams.image = { data: attachedImage.data, mediaType: attachedImage.mediaType };
      }

      const response = await client.queries.agentQuery({
        action: "chat",
        params: JSON.stringify(chatParams),
      });

      // Clear image after sending
      setAttachedImage(null);

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
    // agentMode and attachedImage are read above and belong here. Without them the
    // callback kept whichever values existed when input, messages or t last changed.
    // Typing hid the problem, because each keystroke changes `input` and rebuilds the
    // callback. The task cards do not: they call sendMessage(t(card.promptKey))
    // directly, so attaching an image or switching mode and then clicking a card sent
    // the previous mode and dropped the image.
  }, [input, messages, t, agentMode, attachedImage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const clearHistory = () => { setMessages([]); setError(null); setPendingApproval(null); setCurrentSessionId(""); };
  const handleApprove = () => { setPendingApproval(null); setMessages((prev) => [...prev, { id: generateId(), role: "system", content: `✅ ${t("approvalApproved")}`, timestamp: Date.now() }]); };
  const handleReject = () => { setPendingApproval(null); setMessages((prev) => [...prev, { id: generateId(), role: "system", content: `❌ ${t("approvalRejected")}`, timestamp: Date.now() }]); };

  return (
    <div className="agent-chat">
      {/* Header */}
      <div className="agent-chat-header">
        <h2>🤖 {t("agentTitle")}</h2>
        <div className="agent-header-actions">
          <button className="btn-sm" onClick={() => setShowHistory(!showHistory)} title={t("chatHistoryTitle")}>📜</button>
          {referencedFiles.length > 0 && (
            <button className="btn-sm" onClick={() => setShowFileSidebar(!showFileSidebar)} title={t("sidebarFileInfo")}>📂</button>
          )}
          {messages.length > 0 && (
            <button className="btn-sm" onClick={clearHistory} title={t("agentClear")}>🗑️</button>
          )}
        </div>
      </div>

      {/* Mode Selector */}
      <div className="agent-mode-selector">
        <button
          className={`mode-pill ${agentMode === "kb" ? "active" : ""}`}
          onClick={() => setAgentMode("kb")}
          title={t("modeKbDesc")}
        >
          🧠 {t("modeKb")}
        </button>
        <button
          className={`mode-pill ${agentMode === "agent" ? "active" : ""}`}
          onClick={() => setAgentMode("agent")}
          title={t("modeAgentDesc")}
        >
          📁 {t("modeAgent")}
        </button>
        <button
          className={`mode-pill ${agentMode === "multi" ? "active" : ""}`}
          onClick={() => setAgentMode("multi")}
          title={t("modeMultiDesc")}
        >
          🤖 {t("modeMulti")}
        </button>
      </div>

      {/* Session History Panel */}
      {showHistory && (
        <div className="chat-history-panel">
          <div className="chat-history-header">
            <h4>📜 {t("chatHistoryTitle")}</h4>
            <button className="btn-sm" onClick={() => { clearHistory(); setShowHistory(false); }}>+ {t("chatHistoryNew")}</button>
          </div>
          {sessions.length === 0 ? (
            <p className="chat-history-empty">{t("chatHistoryEmpty")}</p>
          ) : (
            <div className="chat-history-list">
              {sessions.map((s) => (
                <div key={s.sessionId} className={`chat-history-item ${s.sessionId === currentSessionId ? "active" : ""}`}>
                  <button className="chat-history-item-btn" onClick={() => loadSession(s.sessionId)}>
                    <span className="history-title">{s.title}</span>
                    <span className="history-meta">{s.messageCount} msgs · {new Date(s.updatedAt * 1000).toLocaleDateString()}</span>
                  </button>
                  <button className="chat-history-delete" onClick={() => deleteSession(s.sessionId)} title={t("delete")}>×</button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="agent-chat-messages" role="log" aria-label={t("agentTitle")}>
        {messages.length === 0 && !loading && (
          <div className="agent-chat-welcome">
            <div className="agent-welcome-icon">🤖</div>
            <h3>{t("agentWelcomeTitle")}</h3>
            <p>{t("agentWelcomeDesc")}</p>

            {/* Card Grid — Task Examples (filtered by mode) */}
            <div className="agent-card-grid">
              {TASK_CARDS
                .filter((card) => {
                  if (agentMode === "kb") return card.agent === "knowledge-analyst";
                  if (agentMode === "agent") return card.agent === "file-explorer" || card.agent === "safety-controller";
                  return true; // multi: show all
                })
                .map((card) => (
                <button
                  key={card.id}
                  className="agent-task-card"
                  style={{ background: card.color }}
                  onClick={() => sendMessage(t(card.promptKey))}
                >
                  <div className="card-top">
                    <span className="card-icon">{card.icon}</span>
                    <span className="card-agent-tag">{card.agent}</span>
                  </div>
                  <div className="card-title">{t(card.titleKey)}</div>
                  <div className="card-desc">{t(card.descKey)}</div>
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
                <button className="feedback-btn" onClick={() => handleFeedback(msg.id, "positive")} title={t("acGoodResponse")}>👍</button>
                <button className="feedback-btn" onClick={() => handleFeedback(msg.id, "negative")} title={t("acBadResponse")}>👎</button>
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
      <div
        className="agent-chat-input"
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
      >
        {/* Image Preview */}
        {attachedImage && (
          <div className="agent-image-preview">
            <img src={attachedImage.preview} alt="Attached" />
            <button className="agent-image-remove" onClick={() => setAttachedImage(null)}>✕</button>
          </div>
        )}
        <div className="agent-input-row">
          <button
            className="agent-attach-btn"
            onClick={() => fileInputRef.current?.click()}
            title={t("multimodalAttach")}
            disabled={loading}
          >
            📎
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/gif,image/webp"
            onChange={handleFileInput}
            style={{ display: "none" }}
          />
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={attachedImage ? t("multimodalPlaceholder") : t("agentPlaceholder")}
            disabled={loading}
            rows={2}
            aria-label={t("agentInputLabel")}
          />
          <button className="agent-send-btn" onClick={() => sendMessage()} disabled={loading || (!input.trim() && !attachedImage)} aria-label={t("agentSendLabel")}>
            {loading ? "⏳" : "➤"}
          </button>
        </div>
      </div>

      {/* HITL */}
      {pendingApproval && (
        <ActionApproval request={pendingApproval} onApprove={handleApprove} onReject={handleReject} />
      )}

      {/* File Sidebar (permissions) */}
      <AgentFileSidebar
        referencedFiles={referencedFiles}
        visible={showFileSidebar}
        onClose={() => setShowFileSidebar(false)}
      />
    </div>
  );
}
