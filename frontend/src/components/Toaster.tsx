import { useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, AlertTriangle, Info, X } from "lucide-react";
import { subscribe, getToasts, dismissToast, type ToastKind } from "../lib/toast";

const ICON = {
  success: CheckCircle2,
  error: AlertTriangle,
  info: Info,
} as const;

function iconFor(kind: ToastKind) {
  const Icon = ICON[kind];
  return <Icon size={15} />;
}

/** Portal-mounted toast stack. Mounted once at the app root. */
export function Toaster() {
  const toasts = useSyncExternalStore(subscribe, getToasts, getToasts);

  return createPortal(
    <div className="toast-stack" role="region" aria-label="Notifications">
      <AnimatePresence initial={false}>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            className={`toast toast--${t.kind}`}
            role="status"
            aria-live={t.kind === "error" ? "assertive" : "polite"}
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 24 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
          >
            <span className="toast-icon">{iconFor(t.kind)}</span>
            <span className="toast-msg">{t.message}</span>
            <button type="button" className="icon-btn" aria-label="Dismiss" onClick={() => dismissToast(t.id)}>
              <X size={13} />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>,
    document.body,
  );
}
