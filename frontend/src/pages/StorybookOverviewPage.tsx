import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getStorybookOverview } from "../api/storybook";
import type { StorybookOverview } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { useStorybookProjectSse } from "../hooks/useStorybookProjectSse";
import { useStorybookStore } from "../stores/storybookStore";
import "./StorybookOverviewPage.css";

export function StorybookOverviewPage() {
  const { projectId: projectIdParam } = useParams<{ projectId: string }>();
  const projectId = Number(projectIdParam);
  const overviewVersion = useStorybookStore((s) => s.overviewVersion);
  const setOverview = useStorybookStore((s) => s.setOverview);

  useStorybookProjectSse(Number.isFinite(projectId) ? projectId : null);

  const [data, setData] = useState<StorybookOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isFinite(projectId)) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    void getStorybookOverview(projectId)
      .then((overview) => {
        if (!cancelled) {
          setData(overview);
          setOverview(overview);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load storybook");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, overviewVersion, setOverview]);

  if (!Number.isFinite(projectId)) {
    return <p className="text-muted">Invalid project.</p>;
  }

  if (loading) {
    return <p className="storybook-overview__status">Loading storybook…</p>;
  }

  if (error) {
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

  if (!data) {
    return null;
  }

  const base = `/projects/${projectId}/storybook`;

  return (
    <div className="storybook-overview panel">
      <header className="storybook-overview__header">
        <h1 className="storybook-overview__title">Design system</h1>
        <p className="storybook-overview__meta">
          {data.summary.validated} validated · {data.summary.failed} failed ·{" "}
          {data.summary.total} total
        </p>
      </header>

      <section className="storybook-overview__section">
        <h2 className="storybook-overview__label">Tokens</h2>
        <p className="text-muted">
          {Object.keys(data.designTokens).length} design tokens loaded. Full
          token editor — Phase 2.
        </p>
      </section>

      <section className="storybook-overview__section">
        <h2 className="storybook-overview__label">Components</h2>
        <ul className="storybook-overview__list">
          {data.components.map((c) => (
            <li key={c.id}>
              <Link
                to={`${base}/components/${c.id}`}
                className="storybook-overview__link"
              >
                <span>{c.name}</span>
                <StatusBadge status={c.status} />
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
