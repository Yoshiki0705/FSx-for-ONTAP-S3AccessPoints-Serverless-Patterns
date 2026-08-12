/**
 * Transient notices, with an optional way to take the action back.
 *
 * Two gaps this closes. The first is that success was silent: a rename, a move to
 * trash or a bulk run reported nothing when it worked, so the only evidence was
 * the listing redrawing, and a user who looked away could not tell whether the
 * click registered. Failure had a place to appear — an error beside the control —
 * but success did not.
 *
 * The second is that a destructive action had only a confirmation dialog in front
 * of it. A dialog asks before the fact, when the user is least able to judge, and
 * it asks every time; an undo answers after, when the mistake is visible, and
 * costs nothing when there was none. Trash and rename are both reversible here —
 * `restoreFromTrash` puts an object back, and a rename is a rename in the other
 * direction — so the reversal is offered rather than described.
 *
 * Notices are not persisted. One that matters after a reload belongs in the
 * listing or the audit trail, not here.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "../i18n";

/** How a notice reads. An error stays until dismissed; the rest time out. */
export type ToastTone = "success" | "error" | "info";

/** An offer to reverse what the notice reports. */
export interface ToastAction {
  label: string;
  /** Run when the offer is taken. Rejections surface as an error notice. */
  run: () => Promise<void> | void;
}

interface Toast {
  id: number;
  tone: ToastTone;
  message: string;
  action?: ToastAction;
  /** Set while the action is running, so it cannot be taken twice. */
  busy?: boolean;
}

/** How long a notice stays before it withdraws itself. */
const DISMISS_AFTER_MS = 6_000;
/** Longer when there is something to click: the offer has to be reachable. */
const DISMISS_WITH_ACTION_MS = 12_000;

interface ToastContextValue {
  /** Post a notice. Returns its id so a caller can withdraw it early. */
  notify: (toast: Omit<Toast, "id">) => number;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  // Sits inside I18nProvider so the dismiss control is named in the portal's
  // language like every other control.
  const { t } = useTranslation();
  const [toasts, setToasts] = useState<Toast[]>([]);
  // Ids come from a ref rather than the array length: a notice posted while an
  // earlier one is withdrawing would otherwise reuse a live id.
  const nextId = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const notify = useCallback(
    (toast: Omit<Toast, "id">) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev, { ...toast, id }]);
      // An error keeps its place until dismissed. The others describe something
      // that already happened, and a notice that outlives its relevance is a
      // notice people learn to ignore.
      if (toast.tone !== "error") {
        const after = toast.action ? DISMISS_WITH_ACTION_MS : DISMISS_AFTER_MS;
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), after)
        );
      }
      return id;
    },
    [dismiss]
  );

  const runAction = useCallback(
    async (toast: Toast) => {
      if (!toast.action || toast.busy) return;
      // Stops the countdown first: the reversal may take longer than the notice
      // would have lived, and its own result needs somewhere to appear.
      const timer = timers.current.get(toast.id);
      if (timer) {
        clearTimeout(timer);
        timers.current.delete(toast.id);
      }
      setToasts((prev) => prev.map((t) => (t.id === toast.id ? { ...t, busy: true } : t)));
      try {
        await toast.action.run();
        dismiss(toast.id);
      } catch (e) {
        setToasts((prev) =>
          prev.map((t) =>
            t.id === toast.id
              ? {
                  ...t,
                  busy: false,
                  tone: "error",
                  action: undefined,
                  message: e instanceof Error ? e.message : t.message,
                }
              : t
          )
        );
      }
    },
    [dismiss]
  );

  const value = useMemo(() => ({ notify, dismiss }), [notify, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {/* One live region for the lot. Polite rather than assertive: these report
          what already happened, and interrupting a screen reader mid-sentence to
          say "renamed" is worse than waiting for a pause. Errors are given
          role="alert" individually. */}
      <div className="toast-region" role="status" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`toast toast-${toast.tone}`}
            role={toast.tone === "error" ? "alert" : undefined}
          >
            <span className="toast-message">{toast.message}</span>
            {toast.action && (
              <button
                className="toast-action"
                onClick={() => void runAction(toast)}
                disabled={toast.busy}
              >
                {toast.busy ? "…" : toast.action.label}
              </button>
            )}
            <button
              className="toast-close"
              onClick={() => dismiss(toast.id)}
              aria-label={t("toastDismiss")}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/**
 * Post transient notices.
 *
 * Throws outside the provider rather than returning a no-op: a notice that
 * silently fails to appear is the bug this module exists to fix.
 */
export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
