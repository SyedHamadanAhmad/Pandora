import { useMemo } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import { ComponentGrid } from "../features/storybook/ComponentGrid";
import type { StorybookOutletContext } from "../features/storybook/StorybookShell";
import { TokenLanding } from "../features/storybook/TokenLanding";
import { useStorybookStore } from "../stores/storybookStore";
import "./StorybookOverviewPage.css";

export function StorybookOverviewPage() {
  const { projectId: projectIdParam } = useParams<{ projectId: string }>();
  const projectId = Number(projectIdParam);
  const setOverview = useStorybookStore((s) => s.setOverview);
  const { overview, loading } = useOutletContext<StorybookOutletContext>();

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
