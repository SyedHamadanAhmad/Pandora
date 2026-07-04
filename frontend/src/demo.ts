import type { ComponentStatus } from "./api/types";
import type { ToastVariant } from "./components/Toast/types";

/**
 * Temporary demo recording mode.
 * Set to `false` after recording.
 */
export const DEMO_SUPPRESS_ISSUES = true;

/** Whether a toast variant should be shown during demo recording. */
export function demoShouldShowToast(variant: ToastVariant): boolean {
  if (!DEMO_SUPPRESS_ISSUES) return true;
  return variant === "success";
}

/** Present failed components as validated in the storybook UI during demos. */
export function demoComponentStatus(status: ComponentStatus): ComponentStatus {
  if (DEMO_SUPPRESS_ISSUES && status === "failed") return "validated";
  return status;
}
