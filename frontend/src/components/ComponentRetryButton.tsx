import "./ComponentRetryButton.css";

interface ComponentRetryButtonProps {
  onClick: () => void;
  disabled?: boolean;
  busy?: boolean;
  label?: string;
}

/** Compact retry control (refresh-style) for failed component regeneration. */
export function ComponentRetryButton({
  onClick,
  disabled = false,
  busy = false,
  label = "Retry generation",
}: ComponentRetryButtonProps) {
  return (
    <button
      type="button"
      className={`component-retry-btn${busy ? " component-retry-btn--busy" : ""}`}
      onClick={onClick}
      disabled={disabled || busy}
      aria-label={label}
      title={label}
    >
      <span className="component-retry-btn__icon" aria-hidden>
        ↻
      </span>
    </button>
  );
}
