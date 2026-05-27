import { useState } from "react";
import {
  MAX_REFINE_MESSAGE_LEN,
  validateRefineMessage,
} from "../../utils/refineMessage";
import "./RefineComponentPanel.css";

interface RefineComponentPanelProps {
  disabled?: boolean;
  busy?: boolean;
  onSubmit: (message: string) => void | Promise<void>;
}

export function RefineComponentPanel({
  disabled = false,
  busy = false,
  onSubmit,
}: RefineComponentPanelProps) {
  const [message, setMessage] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);

  const handleSubmit = async () => {
    const err = validateRefineMessage(message);
    if (err) {
      setFieldError(err);
      return;
    }
    setFieldError(null);
    await onSubmit(message.trim());
  };

  const remaining = MAX_REFINE_MESSAGE_LEN - message.length;
  const formDisabled = disabled || busy;

  return (
    <section
      className="refine-panel panel"
      aria-labelledby="refine-panel-heading"
    >
      <h2 id="refine-panel-heading" className="refine-panel__title">
        Refine this component
      </h2>
      <p className="refine-panel__hint text-muted">
        Describe what to improve — styling, layout, variants, or fixes. Plain
        text only.
      </p>
      <label className="refine-panel__label" htmlFor="refine-message">
        Your feedback
      </label>
      <textarea
        id="refine-message"
        className="refine-panel__textarea"
        value={message}
        onChange={(e) => {
          setMessage(e.target.value.slice(0, MAX_REFINE_MESSAGE_LEN));
          if (fieldError) setFieldError(null);
        }}
        placeholder="e.g. Increase padding, make the outline variant more distinct, use stronger shadow on hover…"
        rows={4}
        disabled={formDisabled}
        maxLength={MAX_REFINE_MESSAGE_LEN}
      />
      <div className="refine-panel__footer">
        <span className="refine-panel__count text-muted" aria-live="polite">
          {remaining} characters left
        </span>
        {fieldError ? (
          <p className="refine-panel__error" role="alert">
            {fieldError}
          </p>
        ) : null}
        <button
          type="button"
          className="btn btn-cta btn-auto refine-panel__submit"
          onClick={() => void handleSubmit()}
          disabled={formDisabled || !message.trim()}
        >
          {busy ? "Refining…" : "Refine component"}
        </button>
      </div>
    </section>
  );
}
