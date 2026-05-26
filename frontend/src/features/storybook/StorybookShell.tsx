import { Link, Outlet, useParams } from "react-router-dom";
import { useStorybookOverview } from "../../hooks/useStorybookOverview";
import { useStorybookProjectSse } from "../../hooks/useStorybookProjectSse";
import { StorybookSideNav } from "./StorybookSideNav";
import "./StorybookShell.css";

export function StorybookShell() {
  const { projectId: projectIdParam } = useParams<{ projectId: string }>();
  const projectId = Number(projectIdParam);
  const validId = Number.isFinite(projectId) ? projectId : null;

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
        {error ? (
          <div className="storybook-shell__error panel">
            <p role="alert">{error}</p>
            <Link to="/projects" className="text-link text-link--strong">
              Back to projects
            </Link>
          </div>
        ) : (
          <Outlet context={{ overview, loading }} />
        )}
      </div>
    </div>
  );
}
