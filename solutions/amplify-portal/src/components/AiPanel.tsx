import { useState, useCallback } from "react";
import { generateClient } from "aws-amplify/data";
import type { Schema } from "../../amplify/data/resource";

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
          <h3>AI Assistant</h3>
        </div>
        <div className="ai-panel-empty">
          <p>Select a file to ask questions about its content.</p>
          <p className="ai-panel-hint">
            Click any file in the Files tab, then ask questions here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="ai-panel">
      <div className="ai-panel-header">
        <h3>AI Assistant</h3>
        <span className="ai-panel-file" title={selectedFileKey}>
          {selectedFileName}
        </span>
      </div>

      <div className="ai-panel-messages" role="log" aria-label="AI conversation">
        {messages.length === 0 && (
          <div className="ai-panel-hint">
            Ask a question about <strong>{selectedFileName}</strong>
          </div>
        )}
        {messages.map((msg, idx) => (
          <div key={idx} className={`ai-message ai-message-${msg.role}`}>
            <span className="ai-message-role">
              {msg.role === "user" ? "You" : "AI"}
            </span>
            <span className="ai-message-content">{msg.content}</span>
          </div>
        ))}
        {loading && (
          <div className="ai-message ai-message-assistant">
            <span className="ai-message-role">AI</span>
            <span className="ai-message-content ai-loading">Thinking...</span>
          </div>
        )}
      </div>

      {error && <div className="ai-panel-error">{error}</div>}

      <div className="ai-panel-input">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={`Ask about ${selectedFileName}...`}
          disabled={loading}
          rows={2}
          aria-label="Ask a question about the file"
        />
        <button
          onClick={askQuestion}
          disabled={loading || !input.trim()}
          aria-label="Send question"
        >
          {loading ? "..." : "Ask"}
        </button>
      </div>
    </div>
  );
}
