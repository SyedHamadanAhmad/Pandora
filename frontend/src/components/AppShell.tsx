import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { logout } from "../api/auth";
import { listProjects } from "../api/projects";
import type { Project } from "../api/types";
import { setAuthed } from "../routes/ProtectedRoute";
import "./AppShell.css";

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoadingProjects(true);
    void listProjects()
      .then((res) => {
        if (!cancelled) setProjects(res.projects);
      })
      .catch(() => {
        if (!cancelled) setProjects([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingProjects(false);
      });
    return () => {
      cancelled = true;
    };
  }, [location.pathname]);

  const signOut = async () => {
    await logout();
    setAuthed(false);
    navigate("/login");
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/projects" className="app-brand">
          Pandora
        </Link>
        <button
          type="button"
          className="btn-sign-out"
          onClick={() => void signOut()}
        >
          Sign out
        </button>
      </header>

      <div className="app-sidebar-rail" aria-label="Projects navigation">
        <aside className="app-sidebar">
          <h2 className="app-sidebar__heading">Your projects</h2>
          {loadingProjects ? (
            <p className="app-sidebar__empty">Loading…</p>
          ) : projects.length === 0 ? (
            <p className="app-sidebar__empty">No projects yet</p>
          ) : (
            <nav className="app-sidebar__nav">
              <ul className="app-sidebar__list">
                {projects.map((p) => (
                  <li key={p.id}>
                    <NavLink
                      to={`/projects/${p.id}/run`}
                      className={({ isActive }) =>
                        `app-sidebar__link${isActive ? " app-sidebar__link--active" : ""}`
                      }
                      title={p.name}
                    >
                      {p.name}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </nav>
          )}
        </aside>
      </div>

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
