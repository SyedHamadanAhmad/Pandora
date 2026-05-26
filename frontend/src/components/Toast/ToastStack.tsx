import { Toast } from "./Toast";
import type { ToastItem } from "./types";
import "./Toast.css";

interface ToastStackProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}

export function ToastStack({ toasts, onDismiss }: ToastStackProps) {
  if (toasts.length === 0) return null;

  return (
    <div className="toast-stack" aria-label="Notifications">
      {toasts.map((item) => (
        <Toast key={item.id} item={item} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
