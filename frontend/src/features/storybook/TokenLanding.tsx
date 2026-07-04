import { DEMO_SUPPRESS_ISSUES } from "../../demo";
import { useEffect, useMemo, useState } from "react";
import { patchStorybookTokens } from "../../api/storybook";
import type { StorybookOverview } from "../../api/types";
import { ColorSwatch } from "../../components/ColorSwatch";
import { TypographySample } from "../../components/TypographySample";
import { useToast } from "../../components/Toast/ToastContext";
import { resolveTypographyScale } from "../../utils/typographyTokens";
import "./TokenLanding.css";

interface TokenLandingProps {
  projectId: number;
  overview: StorybookOverview;
  onSaved: (overview: StorybookOverview) => void;
}

function pickEditableTokens(
  designTokens: Record<string, unknown>,
  editableKeys: string[],
): Record<string, string> {
  const draft: Record<string, string> = {};
  for (const key of editableKeys) {
    const val = designTokens[key];
    if (typeof val === "string") {
      draft[key] = val;
    }
  }
  return draft;
}

export function TokenLanding({ projectId, overview, onSaved }: TokenLandingProps) {
  const toast = useToast();
  const editableKeys = overview.tokenSchema.editable;

  const [draft, setDraft] = useState<Record<string, string>>(() =>
    pickEditableTokens(overview.designTokens, editableKeys),
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(pickEditableTokens(overview.designTokens, editableKeys));
  }, [overview.designTokens, editableKeys]);

  const typography = useMemo(
    () => resolveTypographyScale(overview.designTokens, overview.globalConfig),
    [overview.designTokens, overview.globalConfig],
  );

  const dirty = useMemo(() => {
    return editableKeys.some(
      (key) => draft[key] !== String(overview.designTokens[key] ?? ""),
    );
  }, [draft, editableKeys, overview.designTokens]);

  const readOnlyColors = useMemo(() => {
    return Object.entries(overview.designTokens).filter(
      ([key, val]) =>
        typeof val === "string" &&
        (val.startsWith("#") || val.startsWith("rgb")) &&
        !editableKeys.includes(key),
    );
  }, [overview.designTokens, editableKeys]);

  const save = async () => {
    setSaving(true);
    try {
      const merged = { ...overview.designTokens, ...draft };
      const res = await patchStorybookTokens(projectId, merged);
      const next: StorybookOverview = {
        ...overview,
        designTokens: res.designTokens,
      };
      onSaved(next);
      toast.success("Design tokens saved");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save tokens";
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="token-landing">
      <header className="token-landing__header">
        <h1 className="token-landing__title">Design system</h1>
        <p className="token-landing__meta">
          {overview.summary.validated + (DEMO_SUPPRESS_ISSUES ? overview.summary.failed : 0)} validated
          {!DEMO_SUPPRESS_ISSUES && overview.summary.failed > 0
            ? ` · ${overview.summary.failed} failed`
            : ""}
          {overview.summary.generating > 0
            ? ` · ${overview.summary.generating} generating`
            : ""}
          {" · "}
          {overview.summary.total} components
        </p>
      </header>

      {editableKeys.length > 0 ? (
        <section className="token-landing__section">
          <div className="token-landing__section-head">
            <h2 className="token-landing__label">Colors</h2>
            <button
              type="button"
              className="btn btn-cta btn-auto"
              disabled={!dirty || saving}
              onClick={() => void save()}
            >
              {saving ? "Saving…" : "Save tokens"}
            </button>
          </div>
          <ul className="token-landing__swatches">
            {editableKeys.map((key) => (
              <li key={key}>
                <ColorSwatch
                  name={key}
                  value={draft[key] ?? ""}
                  editable
                  disabled={saving}
                  onChange={(value) =>
                    setDraft((prev) => ({ ...prev, [key]: value }))
                  }
                />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {readOnlyColors.length > 0 ? (
        <section className="token-landing__section">
          <h2 className="token-landing__label">System colors</h2>
          <ul className="token-landing__swatches">
            {readOnlyColors.map(([name, value]) => (
              <li key={name}>
                <ColorSwatch name={name} value={value} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {overview.tokenSchema.semanticPairs.length > 0 ? (
        <section className="token-landing__section">
          <h2 className="token-landing__label">Semantic pairs</h2>
          <ul className="token-landing__pairs">
            {overview.tokenSchema.semanticPairs.map((pair) => (
              <li key={`${pair.background}-${pair.foreground}`} className="semantic-pair">
                <div
                  className="semantic-pair__sample"
                  style={{
                    background: pair.background,
                    color: pair.foreground,
                  }}
                >
                  Aa
                </div>
                <div className="semantic-pair__meta">
                  <span className="semantic-pair__bg">{pair.background}</span>
                  <span className="semantic-pair__fg">on {pair.foreground}</span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {typography.length > 0 ? (
        <section className="token-landing__section">
          <h2 className="token-landing__label">Typography</h2>
          <ul className="token-landing__typography">
            {typography.map((row) => (
              <li key={row.key}>
                <TypographySample
                  tokenKey={row.key}
                  value={row.value}
                  style={row.sampleStyle}
                />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
