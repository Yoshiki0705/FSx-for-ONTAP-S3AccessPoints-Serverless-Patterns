/**
 * useAiConfidence — interpret AI processing result confidence levels.
 *
 * Maps numeric confidence scores to human-readable labels with
 * actionable guidance (auto-approve / needs review / reject).
 *
 * Based on shared/human_review.py thresholds:
 *   >= 0.85 → AUTO_APPROVE (high confidence)
 *   0.50-0.84 → HUMAN_REVIEW (medium, needs verification)
 *   < 0.50 → REJECT (low confidence, unreliable)
 */

export interface AiResultMetadata {
  modelId: string;         // e.g., "amazon.nova-lite-v1:0"
  temperature?: number;    // e.g., 0.1
  maxTokens?: number;      // e.g., 4096
  confidence?: number;     // 0.0 - 1.0
  processingTimeMs?: number;
}

export type ConfidenceLevel = "high" | "medium" | "low";

export interface ConfidenceAssessment {
  level: ConfidenceLevel;
  label: string;
  labelJa: string;
  action: "AUTO_APPROVE" | "HUMAN_REVIEW" | "REJECT";
  color: string;
}

const THRESHOLDS = {
  HIGH: 0.85,
  MEDIUM: 0.50,
};

export function assessConfidence(score: number | undefined): ConfidenceAssessment {
  if (score === undefined || score === null) {
    return { level: "medium", label: "Unknown", labelJa: "不明", action: "HUMAN_REVIEW", color: "#f59e0b" };
  }
  if (score >= THRESHOLDS.HIGH) {
    return { level: "high", label: "High Confidence", labelJa: "高信頼度", action: "AUTO_APPROVE", color: "#10b981" };
  }
  if (score >= THRESHOLDS.MEDIUM) {
    return { level: "medium", label: "Needs Review", labelJa: "要確認", action: "HUMAN_REVIEW", color: "#f59e0b" };
  }
  return { level: "low", label: "Low Confidence", labelJa: "低信頼度", action: "REJECT", color: "#ef4444" };
}

/**
 * Format model ID for display (strip version suffix for readability)
 * "amazon.nova-lite-v1:0" → "Nova Lite"
 * "anthropic.claude-3-5-haiku-20241022-v1:0" → "Claude 3.5 Haiku"
 */
export function formatModelName(modelId: string): string {
  if (!modelId) return "Unknown";
  if (modelId.includes("nova-lite")) return "Nova Lite";
  if (modelId.includes("nova-pro")) return "Nova Pro";
  if (modelId.includes("nova-micro")) return "Nova Micro";
  if (modelId.includes("claude-3-5-sonnet")) return "Claude 3.5 Sonnet";
  if (modelId.includes("claude-3-5-haiku")) return "Claude 3.5 Haiku";
  if (modelId.includes("claude-3-haiku")) return "Claude 3 Haiku";
  // Fallback: extract readable name
  const parts = modelId.split(".");
  return parts.length > 1 ? parts[1].split("-v")[0].replace(/-/g, " ") : modelId;
}
