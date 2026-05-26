import type { ComponentRow } from "./pipelineRunState";
import "./ComponentBuildList.css";

interface ComponentBuildListProps {
  rows: ComponentRow[];
  componentCount: number;
}

export function ComponentBuildList({ rows, componentCount }: ComponentBuildListProps) {
  const validated = rows.filter((r) => r.status === "validated").length;
  const failed = rows.filter((r) => r.status === "failed").length;

  return (
    <article className="component-build panel" aria-label="Component generation">
      <header className="component-build__header">
        <div>
          <h2 className="component-build__title">Components</h2>
          <p className="component-build__meta">
            {componentCount} planned
            {validated + failed > 0
              ? ` · ${validated} validated${failed > 0 ? ` · ${failed} failed` : ""}`
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
  const statusClass = `component-row component-row--${row.status}`;

  return (
    <li
      className={statusClass}
      title={row.status === "failed" && row.error ? row.error : undefined}
    >
      <span className="component-row__indicator" aria-hidden>
        <RowIndicator status={row.status} />
      </span>
      <span className="component-row__name">{row.name}</span>
      {row.status === "failed" && row.error ? (
        <span className="component-row__error-hint" title={row.error}>
          {row.error}
        </span>
      ) : null}
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
