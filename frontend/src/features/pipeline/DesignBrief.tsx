import type { DesignBriefReadyEvent } from "../../api/types";
import "./DesignBrief.css";

interface DesignBriefProps {
  data: DesignBriefReadyEvent;
}

export function DesignBrief({ data }: DesignBriefProps) {
  const colors = Object.entries(data.colorTokens ?? {});
  const typography = Object.entries(data.typographyScale ?? {});
  const spacing = Object.entries(
    (data.spacingSystem ?? {}) as Record<string, unknown>,
  );

  return (
    <article className="design-brief" aria-label="Design brief">
      <header className="design-brief__header">
        <h2 className="design-brief__title">Design brief</h2>
        {data.tone ? (
          <p className="design-brief__tone">
            Tone: <span>{data.tone}</span>
          </p>
        ) : null}
      </header>

      {colors.length > 0 ? (
        <section className="design-brief__section">
          <h3 className="design-brief__label">Colors</h3>
          <ul className="design-brief__swatches">
            {colors.map(([name, value]) => (
              <li key={name} className="design-brief__swatch">
                <span
                  className="design-brief__swatch-chip"
                  style={{ background: value }}
                  title={value}
                />
                <span className="design-brief__swatch-meta">
                  <span className="design-brief__swatch-name">{name}</span>
                  <span className="design-brief__swatch-value">{value}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {typography.length > 0 ? (
        <section className="design-brief__section">
          <h3 className="design-brief__label">Typography</h3>
          <ul className="design-brief__tokens">
            {typography.map(([name, value]) => (
              <li key={name} className="design-brief__token-row">
                <span className="design-brief__token-name">{name}</span>
                <span
                  className="design-brief__token-value"
                  style={
                    typeof value === "string" && /px|rem|em|%/.test(value)
                      ? { fontSize: value }
                      : undefined
                  }
                >
                  {String(value)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {spacing.length > 0 ? (
        <section className="design-brief__section">
          <h3 className="design-brief__label">Spacing</h3>
          <ul className="design-brief__tokens">
            {spacing.map(([name, value]) => (
              <li key={name} className="design-brief__token-row">
                <span className="design-brief__token-name">{name}</span>
                <span className="design-brief__token-value">
                  {typeof value === "object"
                    ? JSON.stringify(value)
                    : String(value)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {data.componentList.length > 0 ? (
        <section className="design-brief__section">
          <h3 className="design-brief__label">Components planned</h3>
          <ul className="design-brief__chips">
            {data.componentList.map((name) => (
              <li key={name} className="design-brief__chip">
                {name}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {data.inputGaps.length > 0 ? (
        <section className="design-brief__section design-brief__section--gaps">
          <h3 className="design-brief__label">Input gaps</h3>
          <ul className="design-brief__gaps">
            {data.inputGaps.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}
