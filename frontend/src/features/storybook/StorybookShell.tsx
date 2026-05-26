import { Link, Outlet, useParams } from "react-router-dom";
import "./StorybookShell.css";

export function StorybookShell() {
  const { projectId } = useParams<{ projectId: string }>();
  const base = `/projects/${projectId}/storybook`;

  return (
    <div className="storybook-shell">
      <aside className="storybook-shell__nav" aria-label="Storybook navigation">
        <Link to={base} className="storybook-shell__nav-home">
          Design system
        </Link>
        <p className="storybook-shell__nav-hint">
          Component list and workspace — Phase 2+
        </p>
      </aside>
      <div className="storybook-shell__main">
        <Outlet />
      </div>
    </div>
  );
}
