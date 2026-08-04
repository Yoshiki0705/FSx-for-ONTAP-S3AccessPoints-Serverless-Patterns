/**
 * ActionApproval — Human-in-the-Loop modal for dangerous agent actions.
 *
 * When the AI agent proposes a destructive/irreversible operation (delete, lock,
 * block user, enable SnapLock), this modal appears asking the user to confirm.
 *
 * Design (per Bowles/ethics, Norman/feedback):
 * - Clear description of what will happen
 * - Explicit reversibility warning
 * - Reject is the prominent action (safety default)
 * - Approve requires conscious decision
 */
import { useTranslation } from "../i18n";

export interface ApprovalRequest {
  actionType: string;
  target: string;
  reason: string;
  isReversible: boolean;
}

interface ActionApprovalProps {
  request: ApprovalRequest;
  onApprove: () => void;
  onReject: () => void;
}

const ACTION_ICONS: Record<string, string> = {
  delete: "🗑️",
  lock: "🔒",
  block_user: "🚫",
  block_ip: "🚫",
  enable_snaplock: "🔐",
  modify_retention: "⏱️",
  contain_threat: "🛡️",
  unknown: "⚠️",
};

export function ActionApproval({ request, onApprove, onReject }: ActionApprovalProps) {
  const { t } = useTranslation();
  const icon = ACTION_ICONS[request.actionType] || ACTION_ICONS.unknown;

  return (
    <div className="approval-overlay" onClick={onReject}>
      <div className="approval-modal" onClick={(e) => e.stopPropagation()} role="alertdialog" aria-modal="true" aria-labelledby="approval-title">
        <div className="approval-header">
          <span className="approval-icon">{icon}</span>
          <h3 id="approval-title">{t("approvalTitle")}</h3>
        </div>

        <div className="approval-body">
          <p className="approval-description">{t("approvalDesc")}</p>

          <div className="approval-details">
            <div className="approval-detail-row">
              <span className="detail-label">{t("approvalAction")}</span>
              <span className="detail-value">{request.actionType.replace(/_/g, " ")}</span>
            </div>
            <div className="approval-detail-row">
              <span className="detail-label">{t("approvalTarget")}</span>
              <span className="detail-value"><code>{request.target}</code></span>
            </div>
            <div className="approval-detail-row">
              <span className="detail-label">{t("approvalReason")}</span>
              <span className="detail-value">{request.reason}</span>
            </div>
          </div>

          {/* Reversibility warning */}
          {!request.isReversible && (
            <div className="approval-warning">
              <span className="warning-icon">⚠️</span>
              <span>{t("approvalIrreversible")}</span>
            </div>
          )}
        </div>

        <div className="approval-actions">
          <button className="approval-reject-btn" onClick={onReject} autoFocus>
            ❌ {t("approvalReject")}
          </button>
          <button className="approval-approve-btn" onClick={onApprove}>
            ✅ {t("approvalApprove")}
          </button>
        </div>
      </div>
    </div>
  );
}
