/** Matches backend `ReviseComponentRequest` max length. */
export const MAX_REFINE_MESSAGE_LEN = 4096;

const URL_PATTERN =
  /(?:https?:\/\/|www\.)[^\s]+|\b[a-z0-9][-a-z0-9]*\.(com|org|net|io|dev|app|co)\b[^\s]*/i;

const IMAGE_PATTERN =
  /data:image\/[a-z+]+;base64,|\.(png|jpe?g|gif|webp|svg|bmp|ico)(\?[^\s]*)?\b/i;

/**
 * Validate refine/revise message: plain text only (no URLs or image references).
 * Returns an error string, or null if valid.
 */
export function validateRefineMessage(message: string): string | null {
  const text = message.trim();
  if (!text) {
    return "Enter feedback before refining.";
  }
  if (text.length > MAX_REFINE_MESSAGE_LEN) {
    return `Feedback must be at most ${MAX_REFINE_MESSAGE_LEN} characters.`;
  }
  if (URL_PATTERN.test(text)) {
    return "Links and URLs are not allowed — use plain text only.";
  }
  if (IMAGE_PATTERN.test(text)) {
    return "Image references are not allowed — use plain text only.";
  }
  return null;
}

/** Default instruction when retrying a failed component from its error reason. */
export function retryMessageFromError(errorReason: string | null | undefined): string {
  const reason = errorReason?.trim();
  if (reason) {
    return `Fix the following issues and regenerate the component:\n${reason}`;
  }
  return "Regenerate and fix validation errors.";
}
