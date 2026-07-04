import { Link, NavLink, useParams } from "react-router-dom";
import type { StorybookComponentSummary } from "../../api/types";
import { demoComponentStatus } from "../../demo";
import "./StorybookSideNav.css";

function statusIcon(status: StorybookComponentSummary["status"]): string {
  switch (status) {
    case "validated":
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

interface StorybookSideNavProps {
  components: StorybookComponentSummary[];
  loading?: boolean;
}

export function StorybookSideNav({ components, loading }: StorybookSideNavProps) {
  const { projectId } = useParams<{ projectId: string }>();
  const base = `/projects/${projectId}/storybook`;

  return (
    <nav className="storybook-sidenav" aria-label="Storybook">
      <Link to={base} className="storybook-sidenav__home">
        Design system
      </Link>

      <p className="storybook-sidenav__heading">Components</p>

      {loading ? (
        <p className="storybook-sidenav__hint">Loading…</p>
      ) : components.length === 0 ? (
        <p className="storybook-sidenav__hint">No components yet</p>
      ) : (
        <ul className="storybook-sidenav__list">
          {components.map((c) => {
            const displayStatus = demoComponentStatus(c.status);
            return (
            <li key={c.id}>
              <NavLink
                to={`${base}/components/${c.id}`}
                className={({ isActive }) =>
                  `storybook-sidenav__link${isActive ? " storybook-sidenav__link--active" : ""}`
                }
                title={c.name}
              >
                <span
                  className={`storybook-sidenav__icon storybook-sidenav__icon--${displayStatus}`}
                  aria-hidden
                >
                  {statusIcon(displayStatus)}
                </span>
                <span className="storybook-sidenav__name">{c.name}</span>
              </NavLink>
            </li>
            );
          })}
        </ul>
      )}
    </nav>
  );
}
