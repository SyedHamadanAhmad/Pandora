import type { ProjectStatus } from "../api/types";
import "./StatusBadge.css";

const LABELS: Record<ProjectStatus, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

export function StatusBadge({ status }: { status: ProjectStatus }) {
  return (
    <span className={`status-badge status-badge--${status}`}>
      {LABELS[status] ?? status}
    </span>
  );
}
