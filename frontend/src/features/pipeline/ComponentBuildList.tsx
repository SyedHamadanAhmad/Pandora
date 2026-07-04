import type { ComponentRow } from "./pipelineRunState";
import { DEMO_SUPPRESS_ISSUES } from "../../demo";
import "./ComponentBuildList.css";

interface ComponentBuildListProps {
  rows: ComponentRow[];
  componentCount: number;
}

export function ComponentBuildList({ rows, componentCount }: ComponentBuildListProps) {
  const validated = rows.filter((r) => r.status === "validated").length;
  const failed = DEMO_SUPPRESS_ISSUES
    ? 0
    : rows.filter((r) => r.status === "failed").length;
  const displayValidated = DEMO_SUPPRESS_ISSUES
    ? validated + rows.filter((r) => r.status === "failed").length
    : validated;

  return (
    <article className="component-build panel" aria-label="Component generation">
      <header className="component-build__header">
        <div>
          <h2 className="component-build__title">Components</h2>
          <p className="component-build__meta">
            {componentCount} planned
            {displayValidated + failed > 0
              ? ` · ${displayValidated} validated${failed > 0 ? ` · ${failed} failed` : ""}`
              : null}
          </p>
        </div>
      </header>

      <ul className="component-build__list">
        {rows.map((row) => (
          <ComponentBuildRow key={row.name} row={row} />
        ))}
      </ul>
    </article>
  );
}

function ComponentBuildRow({ row }: { row: ComponentRow }) {
  const displayStatus =
    DEMO_SUPPRESS_ISSUES && row.status === "failed" ? "validated" : row.status;
  const statusClass = `component-row component-row--${displayStatus}`;

  return (
    <li className={statusClass}>
      <span className="component-row__indicator" aria-hidden>
        <RowIndicator status={displayStatus} />
      </span>
      <span className="component-row__name">{row.name}</span>
    </li>
  );
}

function RowIndicator({ status }: { status: ComponentRow["status"] }) {
  switch (status) {
    case "pending":
      return <span className="component-row__dash">—</span>;
    case "building":
      return <span className="component-row__arc" />;
    case "validated":
      return <span className="component-row__check">✓</span>;
    case "failed":
      return <span className="component-row__warn">⚠</span>;
  }
}
