import { useState } from "react";
import { useTranslation } from "../i18n";

const STORAGE_KEY = "portal-welcome-dismissed";

/**
 * Welcome Modal — first-time user onboarding.
 *
 * Shows 3 steps: Browse files, AI processing, Data protection.
 * Dismissable with "Don't show again" checkbox.
 * Only renders when localStorage flag is not set.
 */
export function WelcomeModal() {
  const { t } = useTranslation();
  const [dismissed, setDismissed] = useState(() => {
    try { return localStorage.getItem(STORAGE_KEY) === "true"; }
    catch { return false; }
  });
  const [dontShowAgain, setDontShowAgain] = useState(false);
  const [step, setStep] = useState(0);

  if (dismissed) return null;

  const handleDismiss = () => {
    if (dontShowAgain) {
      try { localStorage.setItem(STORAGE_KEY, "true"); } catch { /* noop */ }
    }
    setDismissed(true);
  };

  const steps = [
    { icon: "📂", title: t("welcomeStep1Title"), desc: t("welcomeStep1Desc") },
    { icon: "⚡", title: t("welcomeStep2Title"), desc: t("welcomeStep2Desc") },
    { icon: "🔒", title: t("welcomeStep3Title"), desc: t("welcomeStep3Desc") },
  ];

  return (
    <div className="welcome-overlay" onClick={handleDismiss}>
      <div className="welcome-modal" onClick={(e) => e.stopPropagation()}>
        <h2>{t("welcomeTitle")}</h2>

        <div className="welcome-step">
          <div className="welcome-step-icon">{steps[step].icon}</div>
          <h3>{steps[step].title}</h3>
          <p>{steps[step].desc}</p>
        </div>

        <div className="welcome-dots">
          {steps.map((_, i) => (
            <span key={i} className={`dot ${i === step ? "active" : ""}`} onClick={() => setStep(i)} />
          ))}
        </div>

        <div className="welcome-actions">
          {step < steps.length - 1 ? (
            <button className="btn-primary" onClick={() => setStep(step + 1)}>
              {t("welcomeNext")} →
            </button>
          ) : (
            <button className="btn-primary" onClick={handleDismiss}>
              {t("welcomeStart")} 🚀
            </button>
          )}
        </div>

        <label className="welcome-checkbox">
          <input type="checkbox" checked={dontShowAgain} onChange={(e) => setDontShowAgain(e.target.checked)} />
          {t("welcomeDontShow")}
        </label>
      </div>
    </div>
  );
}
