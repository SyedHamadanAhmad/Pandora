/**
 * Flattens API design tokens into CSS custom properties for Sandpack / :root.
 */

function toVarSegment(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, "$1-$2")
    .replace(/_/g, "-")
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "-")
    .replace(/-+/g, "-");
}

function walkTokens(
  prefix: string,
  value: unknown,
  lines: string[],
  depth: number,
): void {
  if (value == null || depth > 8) return;

  if (typeof value === "string" || typeof value === "number") {
    const name = prefix ? `--${prefix}` : "--token";
    lines.push(`  ${name}: ${String(value)};`);
    return;
  }

  if (typeof value === "boolean") {
    const name = prefix ? `--${prefix}` : "--token";
    lines.push(`  ${name}: ${value ? "1" : "0"};`);
    return;
  }

  if (Array.isArray(value)) {
    return;
  }

  if (typeof value === "object") {
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      const seg = toVarSegment(k);
      const next = prefix ? `${prefix}-${seg}` : seg;
      walkTokens(next, v, lines, depth + 1);
    }
  }
}

/** CSS for Sandpack preview: variables + minimal reset. */
export function designTokensToCss(tokens: Record<string, unknown>): string {
  const lines: string[] = [];
  for (const [key, val] of Object.entries(tokens)) {
    const seg = toVarSegment(key);
    walkTokens(seg, val, lines, 0);
  }

  return `:root {
${lines.join("\n")}
}

*, *::before, *::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

.sandpack-preview-root {
  min-height: 120px;
}
`;
}
