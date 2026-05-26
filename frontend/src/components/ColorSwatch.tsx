import "./ColorSwatch.css";

interface ColorSwatchProps {
  name: string;
  value: string;
  editable?: boolean;
  onChange?: (value: string) => void;
  disabled?: boolean;
}

export function ColorSwatch({
  name,
  value,
  editable = false,
  onChange,
  disabled = false,
}: ColorSwatchProps) {
  return (
    <div className="color-swatch">
      <span
        className="color-swatch__chip"
        style={{ background: value }}
        title={value}
      />
      <div className="color-swatch__meta">
        <span className="color-swatch__name">{name}</span>
        {editable && onChange ? (
          <input
            type="text"
            className="color-swatch__input field-input"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            spellCheck={false}
            aria-label={`${name} color`}
          />
        ) : (
          <span className="color-swatch__value">{value}</span>
        )}
      </div>
    </div>
  );
}
