export type ToastVariant = "success" | "warning" | "error";

export interface ToastItem {
  id: string;
  message: string;
  variant: ToastVariant;
}
