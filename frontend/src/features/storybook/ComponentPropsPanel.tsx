import { useEffect, useState } from "react";
import { sampleForPropKey } from "./mergePreviewProps";
import "./ComponentPropsPanel.css";

interface ComponentPropsPanelProps {
  liveProps: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  variantNames: string[];
  selectedVariant: string;
  onVariantChange: (name: string) => void;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function controlForValue(value: unknown): "json" | "bool" | "text" | "number" {
  if (typeof value === "boolean") return "bool";
  if (typeof value === "number" && !Number.isNaN(value)) return "number";
  if (Array.isArray(value) || isPlainObject(value)) return "json";
  return "text";
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
}

function JsonPropField({
  propKey,
  value,
  onCommit,
}: {
  propKey: string;
  value: unknown;
  onCommit: (v: unknown) => void;
}) {
  const [text, setText] = useState(() => safeStringify(value));

  useEffect(() => {
    setText(safeStringify(value));
  }, [propKey, value]);

  return (
    <textarea
      className="field-input component-props-panel__textarea"
      rows={4}
      spellCheck={false}
      aria-label={`${propKey} as JSON`}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
        const trimmed = text.trim();
        if (!trimmed) {
          onCommit(null);
          return;
        }
        try {
          onCommit(JSON.parse(trimmed) as unknown);
        } catch {
          setText(safeStringify(value));
        }
      }}
    />
  );
}

export function ComponentPropsPanel({
  liveProps,
  onChange,
  variantNames,
  selectedVariant,
  onVariantChange,
}: ComponentPropsPanelProps) {
  const keys = Object.keys(liveProps).sort((a, b) => a.localeCompare(b));

  return (
    <div className="component-props-panel">
      <h2 className="component-props-panel__title">Props</h2>
      <p className="component-props-panel__hint">
        Updates apply to the live preview. Callback props are stubbed inside the sandbox.
      </p>

      {variantNames.length > 1 ? (
        <label className="component-props-panel__field">
          <span className="component-props-panel__label">Variant</span>
          <select
            className="field-input"
            value={selectedVariant}
            onChange={(e) => onVariantChange(e.target.value)}
          >
            {variantNames.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      {keys.length === 0 ? (
        <p className="text-muted">No props on this component.</p>
      ) : (
        <ul className="component-props-panel__list">
          {keys.map((key) => {
            const value = liveProps[key];
            const kind = controlForValue(value);
            return (
              <li key={key} className="component-props-panel__row">
                <div className="component-props-panel__row-head">
                  <span className="component-props-panel__key">{key}</span>
                  {kind === "text" ? (
                    <button
                      type="button"
                      className="component-props-panel__sample text-link"
                      onClick={() =>
                        onChange({ ...liveProps, [key]: sampleForPropKey(key) })
                      }
                    >
                      Sample text
                    </button>
                  ) : null}
                </div>

                {kind === "bool" ? (
                  <label className="component-props-panel__check">
                    <input
                      type="checkbox"
                      checked={Boolean(value)}
                      onChange={(e) =>
                        onChange({ ...liveProps, [key]: e.target.checked })
                      }
                    />
                    <span>{value ? "true" : "false"}</span>
                  </label>
                ) : null}

                {kind === "number" ? (
                  <input
                    type="number"
                    className="field-input"
                    value={typeof value === "number" ? value : Number(value)}
                    onChange={(e) => {
                      const n = e.target.valueAsNumber;
                      onChange({
                        ...liveProps,
                        [key]: Number.isNaN(n) ? 0 : n,
                      });
                    }}
                  />
                ) : null}

                {kind === "text" ? (
                  <input
                    type="text"
                    className="field-input"
                    value={typeof value === "string" ? value : String(value ?? "")}
                    onChange={(e) =>
                      onChange({ ...liveProps, [key]: e.target.value })
                    }
                    spellCheck={false}
                  />
                ) : null}

                {kind === "json" ? (
                  <JsonPropField
                    propKey={key}
                    value={value}
                    onCommit={(parsed) => onChange({ ...liveProps, [key]: parsed })}
                  />
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
