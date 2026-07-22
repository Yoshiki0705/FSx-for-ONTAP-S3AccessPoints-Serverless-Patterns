import { useState, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";
import { useTranslation } from "../i18n";

const client = generateClient<Schema>();

interface AiPanelProps {
  /** Currently selected file key (full S3 path) */
  selectedFileKey: string | null;
  /** File name for display */
  selectedFileName: string | null;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

/**
 * AI Panel — Ask questions about files using Amazon Bedrock.
 *
 * Architecture:
 *   User types question → AppSync askAboutFile mutation
 *   → Lambda → S3 AP GetObject (file content) → Bedrock InvokeModel
 *   → Answer returned and displayed
 *
 * The panel appears alongside the file explorer and operates on
 * the currently selected file.
 */
export function AiPanel({ selectedFileKey, selectedFileName }: AiPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { t } = useTranslation();

  const askQuestion = useCallback(async () => {
    if (!input.trim() || !selectedFileKey) return;

    const question = input.trim();
    setInput("");
    setError(null);

    // Add user message
    const userMsg: ChatMessage = { role: "user", content: question, timestamp: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const response = await client.mutations.askAboutFile({
        key: selectedFileKey,
        question,
      });

      if (response.data?.error) {
        setError(response.data.error);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `Error: ${response.data!.error}`, timestamp: Date.now() },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: response.data?.answer || "No response received.",
            timestamp: Date.now(),
          },
        ]);
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Failed to get AI response";
      setError(errMsg);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${errMsg}`, timestamp: Date.now() },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, selectedFileKey]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      askQuestion();
    }
  };

  if (!selectedFileKey) {
    return (
      <div className="ai-panel">
        <div className="ai-panel-header">
          <h3>{t("aiTitle")}</h3>
        </div>
        <div className="ai-panel-empty">
          <p>{t("aiEmptyState")}</p>
          <p className="ai-panel-hint">{t("aiEmptyHint")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="ai-panel">
      <div className="ai-panel-header">
        <h3>{t("aiTitle")}</h3>
        <span className="ai-panel-file" title={selectedFileKey}>
          {selectedFileName}
        </span>
      </div>

      <div className="ai-panel-messages" role="log" aria-label={t("aiTitle")}>
        {messages.length === 0 && (
          <div className="ai-panel-hint">
            {t("aiAskHint")} <strong>{selectedFileName}</strong>
          </div>
        )}
        {messages.map((msg, idx) => (
          <div key={idx} className={`ai-message ai-message-${msg.role}`}>
            <span className="ai-message-role">
              {msg.role === "user" ? t("aiYou") : t("aiAssistant")}
            </span>
            <span className="ai-message-content">{msg.content}</span>
          </div>
        ))}
        {loading && (
          <div className="ai-message ai-message-assistant">
            <span className="ai-message-role">{t("aiAssistant")}</span>
            <span className="ai-message-content ai-loading">{t("aiThinking")}</span>
          </div>
        )}
      </div>

      {error && <div className="ai-panel-error">{error}</div>}

      <div className="ai-panel-input">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={`${t("aiPlaceholder")} ${selectedFileName}...`}
          disabled={loading}
          rows={2}
          aria-label={t("aiInputLabel")}
        />
        <button
          onClick={askQuestion}
          disabled={loading || !input.trim()}
          aria-label={t("aiSendLabel")}
        >
          {loading ? t("aiAskBtnLoading") : t("aiAskBtn")}
        </button>
      </div>
    </div>
  );
}
