import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { ComponentGrid } from "../features/storybook/ComponentGrid";
import { TokenLanding } from "../features/storybook/TokenLanding";
import { useStorybookOverview } from "../hooks/useStorybookOverview";
import { useStorybookStore } from "../stores/storybookStore";
import "./StorybookOverviewPage.css";

export function StorybookOverviewPage() {
  const { projectId: projectIdParam } = useParams<{ projectId: string }>();
  const projectId = Number(projectIdParam);
  const setOverview = useStorybookStore((s) => s.setOverview);

  const { overview, loading, error } = useStorybookOverview(
    Number.isFinite(projectId) ? projectId : null,
  );

  const specsByName = useMemo(() => {
    const map = new Map<string, { type?: string | null; variants: string[] }>();
    if (!overview) return map;
    for (const spec of overview.componentSpecs) {
      map.set(spec.name, { type: spec.type, variants: spec.variants });
    }
    return map;
  }, [overview]);

  if (!Number.isFinite(projectId)) {
    return <p className="text-muted">Invalid project.</p>;
  }

  if (loading && !overview) {
    return <p className="storybook-overview__status">Loading storybook…</p>;
  }

  if (error && !overview) {
    return (
      <div className="storybook-overview panel">
        <p className="storybook-overview__error" role="alert">
          {error}
        </p>
        <Link to="/projects" className="text-link text-link--strong">
          Back to projects
        </Link>
      </div>
    );
  }

  if (!overview) {
    return null;
  }

  return (
    <div className="storybook-overview">
      <TokenLanding
        projectId={projectId}
        overview={overview}
        onSaved={(next) => setOverview(next)}
      />
      <ComponentGrid
        projectId={projectId}
        components={overview.components}
        specsByName={specsByName}
      />
    </div>
  );
}
