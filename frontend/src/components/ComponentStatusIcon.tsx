import type { ComponentStatus } from "../api/types";
import { demoComponentStatus } from "../demo";
import "./ComponentStatusIcon.css";

const LABELS: Record<ComponentStatus, string> = {
  pending: "Pending",
  generating: "Generating",
  validating: "Validating",
  validated: "Validated",
  failed: "Failed",
  revised: "Revised",
};

function iconChar(status: ComponentStatus): string {
  switch (status) {
    case "validated":
    case "revised":
      return "✓";
    case "failed":
      return "⚠";
    case "generating":
    case "validating":
      return "◌";
    default:
      return "—";
  }
}

export function ComponentStatusIcon({ status }: { status: ComponentStatus }) {
  const display = demoComponentStatus(status);
  return (
    <span
      className={`component-status-icon component-status-icon--${display}`}
      title={LABELS[display]}
      aria-label={LABELS[display]}
    >
      {iconChar(display)}
    </span>
  );
}
