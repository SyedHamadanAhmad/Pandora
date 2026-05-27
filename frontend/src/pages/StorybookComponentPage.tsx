import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getComponentDetail } from "../api/storybook";
import type { ComponentDetailResponse } from "../api/types";
import { ComponentPropsPanel } from "../features/storybook/ComponentPropsPanel";
import {
  computeMergedProps,
  listVariantNames,
} from "../features/storybook/mergePreviewProps";
import { StatusBadge } from "../components/StatusBadge";
import { useStorybookOverview } from "../hooks/useStorybookOverview";
import { useStorybookStore } from "../stores/storybookStore";
import "./StorybookComponentPage.css";

const ComponentSandpack = lazy(() =>
  import("../features/storybook/ComponentSandpack").then((m) => ({
    default: m.ComponentSandpack,
  })),
);

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

  const [selectedVariant, setSelectedVariant] = useState("default");
  const [liveProps, setLiveProps] = useState<Record<string, unknown>>({});

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

  const variantNames = useMemo(() => {
    if (!data) return ["default"];
    return listVariantNames(data.component, data.spec);
  }, [data]);

  useEffect(() => {
    if (!data) return;
    const names = listVariantNames(data.component, data.spec);
    const first = names[0] ?? "default";
    setSelectedVariant(first);
    setLiveProps(computeMergedProps(data.component, data.spec, first));
  }, [data, overviewVersion]);

  const applyVariant = useCallback(
    (name: string) => {
      if (!data) return;
      setSelectedVariant(name);
      setLiveProps(computeMergedProps(data.component, data.spec, name));
    },
    [data],
  );

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

  const { component, designTokens, spec } = data;
  const tsx = component.tsxCode?.trim();
  const canPreview =
    Boolean(tsx) &&
    (component.status === "validated" ||
      component.status === "revised" ||
      component.status === "failed");

  const sandpackKey = `${component.id}-${component.updatedAt}-${tsx?.length ?? 0}`;

  return (
    <div className="storybook-workspace">
      <header className="storybook-workspace__header">
        <Link to={overviewHref} className="storybook-workspace__back">
          ← Design system
        </Link>
        <div className="storybook-workspace__title-row">
          <h1 className="storybook-workspace__title">{component.name}</h1>
          <StatusBadge status={component.status} />
        </div>
        {component.errorReason ? (
          <p className="storybook-workspace__error" role="status">
            {component.errorReason}
          </p>
        ) : null}
      </header>

      <div className="storybook-workspace__split">
        <section
          className="storybook-workspace__preview"
          aria-label="Live preview"
        >
          {!tsx ? (
            <div className="storybook-workspace__placeholder panel">
              <p className="text-muted">No preview code yet.</p>
            </div>
          ) : component.status === "generating" || component.status === "validating" ? (
            <div className="storybook-workspace__placeholder panel">
              <p>Preview will be available when generation finishes.</p>
            </div>
          ) : canPreview ? (
            <Suspense
              fallback={
                <div className="storybook-workspace__placeholder panel">
                  <p className="text-muted">Loading preview…</p>
                </div>
              }
            >
              <ComponentSandpack
                sandpackKey={sandpackKey}
                componentName={component.name}
                tsxCode={tsx}
                cssCode={component.cssCode}
                designTokens={designTokens}
                previewProps={liveProps}
              />
            </Suspense>
          ) : (
            <div className="storybook-workspace__placeholder panel">
              <p className="text-muted">Preview is not available for this status.</p>
              <pre className="storybook-component__preview-snippet">
                <code>{tsx.slice(0, 2000)}</code>
                {tsx.length > 2000 ? "…" : ""}
              </pre>
            </div>
          )}
        </section>

        <aside
          className="storybook-workspace__controls panel"
          aria-label="Component props"
        >
          <ComponentPropsPanel
            liveProps={liveProps}
            onChange={setLiveProps}
            variantNames={variantNames}
            selectedVariant={selectedVariant}
            onVariantChange={applyVariant}
          />
        </aside>
      </div>
    </div>
  );
}
