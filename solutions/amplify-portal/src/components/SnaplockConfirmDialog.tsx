/**
 * Confirmation step for SnapLock settings, stated as consequences.
 *
 * The forms it guards used to submit straight from the button, so the operator
 * saw the values they had entered and never the effect of entering them. This
 * dialog restates the same input as what becomes undeletable, until which date,
 * and which parts cannot be undone — and for the irreversible ones it asks for a
 * typed word so the action cannot happen by clicking through a modal.
 *
 * The wording comes from `describeConsequences`, so the rules are testable
 * without rendering and the dialog only decides presentation.
 */

import { useState } from "react";
import { useTranslation } from "../i18n";
import {
  SNAPLOCK_CONFIRM_KEYWORD,
  confirmationLevel,
  describeConsequences,
  headlineUntil,
  intentSubject,
  type SnaplockConsequence,
  type SnaplockIntent,
  type SnaplockSeverity,
} from "../utils/snaplockConsequences";

interface SnaplockConfirmDialogProps {
  intent: SnaplockIntent;
  onConfirm: () => void;
  onCancel: () => void;
  /** Frozen clock for tests. Defaults to now. */
  now?: Date;
}

const SEVERITY_ICON: Record<SnaplockSeverity, string> = {
  irreversible: "⛔",
  blocksDeletion: "🔒",
  info: "ℹ️",
};

/** Locale-formatted absolute date. Falls back to the ISO string. */
function formatDate(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  try {
    return date.toLocaleDateString(locale, {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  } catch {
    return date.toISOString().slice(0, 10);
  }
}

export function SnaplockConfirmDialog({
  intent,
  onConfirm,
  onCancel,
  now,
}: SnaplockConfirmDialogProps) {
  const { t, locale } = useTranslation();
  const [typed, setTyped] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);

  const at = now ?? new Date();
  const consequences = describeConsequences(intent, at);
  const level = confirmationLevel(intent);
  const until = headlineUntil(intent, at);

  const ready =
    level === "keyword" ? typed.trim() === SNAPLOCK_CONFIRM_KEYWORD : acknowledged;

  const render = (c: SnaplockConsequence, index: number) => {
    const values = { ...(c.values ?? {}) };
    if (typeof values.date === "string") {
      values.date = formatDate(values.date, locale);
    }
    let text = t(c.messageKey);
    for (const [key, value] of Object.entries(values)) {
      text = text.split(`{${key}}`).join(String(value));
    }
    return (
      <li key={`${c.messageKey}-${index}`} className={`slc-item slc-${c.severity}`}>
        <span className="slc-icon" aria-hidden="true">
          {SEVERITY_ICON[c.severity]}
        </span>
        <span className="slc-text">{text}</span>
      </li>
    );
  };

  return (
    <div
      className="slc-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="slc-title"
    >
      <div className="slc-dialog">
        <h3 id="slc-title" className="slc-title">
          {t("slcTitle")}
        </h3>

        <p className="slc-subject">
          {t("slcSubject").split("{name}").join(intentSubject(intent))}
        </p>

        {/* The date first and on its own line: it is the one value an operator
            can check against the console, and a duration is not. */}
        {until && (
          <p className="slc-until">
            {t("slcUntilHeadline")
              .split("{date}")
              .join(formatDate(until.toISOString(), locale))}
          </p>
        )}

        <ul className="slc-list">{consequences.map(render)}</ul>

        <p className="slc-docs">{t("slcSeeDocs")}</p>

        {level === "keyword" ? (
          <div className="slc-gate">
            <label htmlFor="slc-keyword">
              {t("slcTypeToConfirm").split("{keyword}").join(SNAPLOCK_CONFIRM_KEYWORD)}
            </label>
            <input
              id="slc-keyword"
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
              spellCheck={false}
              aria-describedby="slc-keyword-hint"
            />
            <small id="slc-keyword-hint" className="slc-hint">
              {t("slcKeywordHint").split("{keyword}").join(SNAPLOCK_CONFIRM_KEYWORD)}
            </small>
          </div>
        ) : (
          <div className="slc-gate">
            <label className="slc-checkbox">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
              />
              <span>{t("slcAcknowledge")}</span>
            </label>
          </div>
        )}

        <div className="slc-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            {t("slcCancel")}
          </button>
          <button
            type="button"
            className="slc-proceed"
            disabled={!ready}
            onClick={onConfirm}
          >
            {t("slcProceed")}
          </button>
        </div>
      </div>
    </div>
  );
}
