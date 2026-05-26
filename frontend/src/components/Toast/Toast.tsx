import type { ToastItem } from "./types";
import "./Toast.css";

interface ToastProps {
  item: ToastItem;
  onDismiss: (id: string) => void;
}

const VARIANT_LABEL: Record<ToastItem["variant"], string> = {
  success: "Success",
  warning: "Warning",
  error: "Error",
};

export function Toast({ item, onDismiss }: ToastProps) {
  return (
    <div
      className={`toast toast--${item.variant}`}
      role={item.variant === "error" ? "alert" : "status"}
      aria-live="polite"
    >
      <span className="toast__indicator" aria-hidden />
      <div className="toast__body">
        <p className="toast__label">{VARIANT_LABEL[item.variant]}</p>
        <p className="toast__message">{item.message}</p>
      </div>
      <button
        type="button"
        className="toast__close"
        aria-label="Dismiss"
        onClick={() => onDismiss(item.id)}
      >
        ×
      </button>
    </div>
  );
}
