import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getComponentDetail } from "../api/storybook";
import type { ComponentDetailResponse } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { useStorybookOverview } from "../hooks/useStorybookOverview";
import { useStorybookStore } from "../stores/storybookStore";
import "./StorybookComponentPage.css";

export function StorybookComponentPage() {
  const { projectId: projectIdParam, componentId: componentIdParam } =
    useParams<{ projectId: string; componentId: string }>();
  const projectId = Number(projectIdParam);
  const componentId = Number(componentIdParam);
  const overviewVersion = useStorybookStore((s) => s.overviewVersion);

  useStorybookOverview(Number.isFinite(projectId) ? projectId : null);

  const [data, setData] = useState<ComponentDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isFinite(projectId) || !Number.isFinite(componentId)) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    void getComponentDetail(projectId, componentId)
      .then((detail) => {
        if (!cancelled) setData(detail);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load component");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, componentId, overviewVersion]);

  if (!Number.isFinite(projectId) || !Number.isFinite(componentId)) {
    return <p className="text-muted">Invalid project or component.</p>;
  }

  const overviewHref = `/projects/${projectId}/storybook`;

  if (loading && !data) {
    return <p className="storybook-component__status">Loading component…</p>;
  }

  if (error && !data) {
    return (
      <div className="storybook-component panel">
        <p className="storybook-component__error" role="alert">
          {error}
        </p>
        <Link to={overviewHref} className="text-link text-link--strong">
          Back to design system
        </Link>
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const { component } = data;

  return (
    <div className="storybook-component panel">
      <header className="storybook-component__header">
        <Link to={overviewHref} className="storybook-component__back">
          ← Design system
        </Link>
        <div className="storybook-component__title-row">
          <h1 className="storybook-component__title">{component.name}</h1>
          <StatusBadge status={component.status} />
        </div>
        <p className="storybook-component__meta">
          Sandpack preview and Props / Suggest — Phase 3.
        </p>
      </header>

      {component.tsxCode ? (
        <pre className="storybook-component__preview-snippet">
          <code>{component.tsxCode.slice(0, 1200)}</code>
          {component.tsxCode.length > 1200 ? "…" : ""}
        </pre>
      ) : (
        <p className="text-muted">No preview code yet.</p>
      )}
    </div>
  );
}
