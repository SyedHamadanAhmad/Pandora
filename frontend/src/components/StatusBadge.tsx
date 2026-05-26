import type { ComponentStatus, ProjectStatus } from "../api/types";
import "./StatusBadge.css";

type BadgeStatus = ProjectStatus | ComponentStatus;

const LABELS: Record<string, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  generating: "Generating",
  validating: "Validating",
  validated: "Validated",
  revised: "Revised",
};

export function StatusBadge({ status }: { status: BadgeStatus }) {
  return (
    <span className={`status-badge status-badge--${status}`}>
      {LABELS[status] ?? status}
    </span>
  );
}
