import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createProject, listProjects } from "../api/projects";
import { createThreadMessage } from "../api/thread";
import type { Project } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import "./ProjectsPage.css";

export function ProjectsPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    const res = await listProjects();
    setProjects(res.projects);
  };

  useEffect(() => {
    void load()
      .catch(() => setError("Failed to load projects"))
      .finally(() => setLoadingList(false));
  }, []);

  const createAndRun = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !prompt.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const project = await createProject(name.trim());
      await createThreadMessage(project.id, prompt.trim());
      navigate(`/projects/${project.id}/run`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start pipeline");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="projects-page">
      <header className="page-intro">
        <h1 className="page-title">Projects</h1>
        <p className="page-lead">
          Describe what you want to build. Pandora runs the pipeline and opens
          your storybook when components are ready.
        </p>
      </header>

      <section className="panel new-project-panel" aria-labelledby="new-project-heading">
        <h2 id="new-project-heading" className="panel-title">
          New project
        </h2>
        <p className="panel-desc">
          Name your project and paste a design prompt to start parsing and
          generation.
        </p>

        <form className="new-project-form" onSubmit={(e) => void createAndRun(e)}>
          <div className="field">
            <label className="field-label" htmlFor="project-name">
              Project name
            </label>
            <input
              id="project-name"
              className="field-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Marketing site"
              required
              disabled={loading}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="design-prompt">
              Design prompt
            </label>
            <textarea
              id="design-prompt"
              className="field-input field-textarea"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the UI, brand feel, and components you need…"
              required
              disabled={loading}
            />
          </div>

          {error && (
            <p className="form-message form-message--error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="btn btn-cta" disabled={loading}>
            {loading ? "Starting pipeline…" : "Create & run pipeline"}
          </button>
        </form>
      </section>

      <section className="section project-list-section" aria-labelledby="recent-heading">
        <h2 id="recent-heading" className="section-title">
          Recent projects
        </h2>

        {loadingList ? (
          <p className="text-muted">Loading projects…</p>
        ) : projects.length === 0 ? (
          <p className="text-muted">
            No projects yet. Create one above to start your first pipeline.
          </p>
        ) : (
          <ul className="project-list">
            {projects.map((p) => (
              <li key={p.id} className="project-card">
                <div className="project-card-main">
                  <div className="project-card-title-row">
                    <h3 className="project-card-name">{p.name}</h3>
                    <StatusBadge status={p.status} />
                  </div>
                  <p className="project-card-meta">
                    Updated {formatDate(p.updatedAt)}
                  </p>
                </div>
                <div className="project-card-actions">
                  <Link
                    to={`/projects/${p.id}/run`}
                    className="text-link text-link--strong"
                  >
                    Pipeline
                  </Link>
                  <Link
                    to={`/projects/${p.id}/storybook`}
                    className="text-link text-link--strong"
                  >
                    Storybook
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}
