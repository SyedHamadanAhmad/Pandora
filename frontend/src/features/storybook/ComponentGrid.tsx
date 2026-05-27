import { Link } from "react-router-dom";
import type { StorybookComponentSummary } from "../../api/types";
import { ComponentRetryButton } from "../../components/ComponentRetryButton";
import { ComponentStatusIcon } from "../../components/ComponentStatusIcon";
import { useReviseComponent } from "../../hooks/useReviseComponent";
import { retryMessageFromError } from "../../utils/refineMessage";
import "./ComponentGrid.css";

interface ComponentGridProps {
  projectId: number;
  components: StorybookComponentSummary[];
  specsByName: Map<string, { type?: string | null; variants: string[] }>;
}

export function ComponentGrid({
  projectId,
  components,
  specsByName,
}: ComponentGridProps) {
  const base = `/projects/${projectId}/storybook`;
  const { revise, isRevisePending } = useReviseComponent(projectId);

  if (components.length === 0) {
    return (
      <p className="component-grid__empty text-muted">
        No components in this library yet.
      </p>
    );
  }

  return (
    <section className="component-grid" aria-labelledby="component-grid-heading">
      <h2 id="component-grid-heading" className="component-grid__title">
        Components
      </h2>
      <ul className="component-grid__list">
        {components.map((component) => {
          const spec = specsByName.get(component.name);
          const showRetry = component.status === "failed";
          const retryBusy = isRevisePending(component.id);
          const isBusy =
            retryBusy ||
            component.status === "generating" ||
            component.status === "validating";

          const handleRetry = () => {
            void revise(
              component.id,
              retryMessageFromError(component.errorReason),
            );
          };

          return (
            <li key={component.id}>
              <article className="component-grid__card">
                <div className="component-grid__card-top">
                  <Link
                    to={`${base}/components/${component.id}`}
                    className="component-grid__name-link"
                  >
                    <span className="component-grid__name">{component.name}</span>
                  </Link>
                  <div className="component-grid__actions">
                    {showRetry ? (
                      <ComponentRetryButton
                        onClick={handleRetry}
                        busy={retryBusy}
                        disabled={isBusy && !retryBusy}
                      />
                    ) : null}
                    <ComponentStatusIcon status={component.status} />
                  </div>
                </div>
                <Link
                  to={`${base}/components/${component.id}`}
                  className="component-grid__card-link"
                >
                  {spec?.type ? (
                    <p className="component-grid__type">{spec.type}</p>
                  ) : null}
                  {spec && spec.variants.length > 0 ? (
                    <ul className="component-grid__variants">
                      {spec.variants.slice(0, 4).map((v) => (
                        <li key={v} className="component-grid__variant">
                          {v}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {component.errorReason ? (
                    <p
                      className="component-grid__error"
                      title={component.errorReason}
                    >
                      {component.errorReason}
                    </p>
                  ) : null}
                </Link>
              </article>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
