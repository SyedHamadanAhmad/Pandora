import { DEMO_SUPPRESS_ISSUES } from "../../demo";
import { useEffect } from "react";
import { Link, Outlet, useParams } from "react-router-dom";
import type { StorybookOverview } from "../../api/types";
import { useStorybookOverview } from "../../hooks/useStorybookOverview";
import { useStorybookProjectSse } from "../../hooks/useStorybookProjectSse";
import { useStorybookStore } from "../../stores/storybookStore";
import { StorybookSideNav } from "./StorybookSideNav";
import "./StorybookShell.css";

export interface StorybookOutletContext {
  overview: StorybookOverview | null;
  loading: boolean;
}

export function StorybookShell() {
  const { projectId: projectIdParam } = useParams<{ projectId: string }>();
  const projectId = Number(projectIdParam);
  const validId = Number.isFinite(projectId) ? projectId : null;
  const resetStorybook = useStorybookStore((s) => s.reset);

  useEffect(() => {
    resetStorybook();
  }, [validId, resetStorybook]);

  useStorybookProjectSse(validId);
  const { overview, loading, error } = useStorybookOverview(validId);

  return (
    <div className="storybook-shell">
      <aside className="storybook-shell__nav" aria-label="Storybook navigation">
        <StorybookSideNav
          components={overview?.components ?? []}
          loading={loading}
        />
      </aside>

      <div className="storybook-shell__main">
        {error && !DEMO_SUPPRESS_ISSUES ? (
          <div className="storybook-shell__error panel">
            <p role="alert">{error}</p>
            <Link to="/projects" className="text-link text-link--strong">
              Back to projects
            </Link>
          </div>
        ) : (
          <Outlet context={{ overview, loading } satisfies StorybookOutletContext} />
        )}
      </div>
    </div>
  );
}
