import type { CSSProperties } from "react";

export interface TypographyTokenRow {
  key: string;
  value: string;
  sampleStyle?: CSSProperties;
}

const STYLE_PROP_KEYS = new Set([
  "fontSize",
  "font_size",
  "fontWeight",
  "font_weight",
  "lineHeight",
  "line_height",
  "fontFamily",
  "font_family",
  "letterSpacing",
  "letter_spacing",
]);

function toCssProperty(key: string): keyof CSSProperties | null {
  switch (key) {
    case "fontSize":
    case "font_size":
      return "fontSize";
    case "fontWeight":
    case "font_weight":
      return "fontWeight";
    case "lineHeight":
    case "line_height":
      return "lineHeight";
    case "fontFamily":
    case "font_family":
      return "fontFamily";
    case "letterSpacing":
    case "letter_spacing":
      return "letterSpacing";
    default:
      return null;
  }
}

function isScalar(value: unknown): value is string | number | boolean {
  return (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  );
}

function isTypographyStyleObject(obj: Record<string, unknown>): boolean {
  return Object.keys(obj).some((k) => STYLE_PROP_KEYS.has(k));
}

function styleFromObject(obj: Record<string, unknown>): CSSProperties {
  const style: CSSProperties = {};
  for (const [key, raw] of Object.entries(obj)) {
    const prop = toCssProperty(key);
    if (prop && isScalar(raw)) {
      (style as Record<string, string | number>)[prop] = raw as string | number;
    }
  }
  return style;
}

function formatStyleObject(obj: Record<string, unknown>): string {
  const order = [
    "fontSize",
    "font_size",
    "fontFamily",
    "font_family",
    "fontWeight",
    "font_weight",
    "lineHeight",
    "line_height",
    "letterSpacing",
    "letter_spacing",
  ];
  const parts: string[] = [];
  for (const key of order) {
    const val = obj[key];
    if (isScalar(val)) {
      parts.push(String(val));
    }
  }
  if (parts.length > 0) return parts.join(" · ");
  return Object.entries(obj)
    .filter(([, v]) => isScalar(v))
    .map(([k, v]) => `${k}: ${v}`)
    .join(", ");
}

/** Human-readable display for a token value (never `[object Object]`). */
export function formatTypographyValue(raw: unknown): string {
  if (raw == null) return "";
  if (isScalar(raw)) return String(raw);
  if (typeof raw === "object" && !Array.isArray(raw)) {
    const obj = raw as Record<string, unknown>;
    if (isTypographyStyleObject(obj)) {
      return formatStyleObject(obj);
    }
    const scalarEntries = Object.entries(obj).filter(([, v]) => isScalar(v));
    if (scalarEntries.length > 0) {
      return scalarEntries.map(([k, v]) => `${k}: ${v}`).join(", ");
    }
    try {
      return JSON.stringify(obj);
    } catch {
      return "";
    }
  }
  return String(raw);
}

function expandTypographyEntries(
  rows: TypographyTokenRow[],
  seen: Set<string>,
  prefix: string,
  raw: unknown,
): void {
  if (raw == null) return;

  const key = prefix;

  if (isScalar(raw)) {
    if (seen.has(key)) return;
    seen.add(key);
    const value = String(raw);
    const sampleStyle: CSSProperties = {};
    const prop = toCssProperty(prefix.split(".").pop() ?? prefix);
    if (prop && /px|rem|em|%/.test(value)) {
      (sampleStyle as Record<string, string>)[prop] = value;
    } else if (prop === "fontFamily") {
      sampleStyle.fontFamily = value;
    } else if (prop === "fontWeight") {
      sampleStyle.fontWeight = value as CSSProperties["fontWeight"];
    } else if (prop === "lineHeight") {
      sampleStyle.lineHeight = value as CSSProperties["lineHeight"];
    } else if (/px|rem|em|%/.test(value)) {
      sampleStyle.fontSize = value;
    }
    rows.push({ key, value, sampleStyle });
    return;
  }

  if (typeof raw !== "object" || Array.isArray(raw)) return;
  const obj = raw as Record<string, unknown>;

  if (isTypographyStyleObject(obj)) {
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({
      key,
      value: formatStyleObject(obj),
      sampleStyle: styleFromObject(obj),
    });
    return;
  }

  for (const [childKey, childVal] of Object.entries(obj)) {
    const childPrefix = prefix ? `${prefix}.${childKey}` : childKey;
    expandTypographyEntries(rows, seen, childPrefix, childVal);
  }
}

function collectFromRecord(
  rows: TypographyTokenRow[],
  seen: Set<string>,
  record: Record<string, unknown> | undefined,
): void {
  if (!record || typeof record !== "object") return;
  for (const [key, val] of Object.entries(record)) {
    expandTypographyEntries(rows, seen, key, val);
  }
}

export function resolveTypographyScale(
  designTokens: Record<string, unknown>,
  globalConfig: Record<string, unknown>,
): TypographyTokenRow[] {
  const rows: TypographyTokenRow[] = [];
  const seen = new Set<string>();

  const nested = designTokens.typography;
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    collectFromRecord(rows, seen, nested as Record<string, unknown>);
  }

  const globalScale = globalConfig.typographyScale;
  if (globalScale && typeof globalScale === "object" && !Array.isArray(globalScale)) {
    collectFromRecord(rows, seen, globalScale as Record<string, unknown>);
  }

  const fontSans =
    typeof designTokens.fontSans === "string"
      ? designTokens.fontSans
      : typeof designTokens.font_sans === "string"
        ? designTokens.font_sans
        : undefined;

  for (const [key, val] of Object.entries(designTokens)) {
    if (key === "typography" || key === "spacing") continue;
    if (!key.toLowerCase().includes("font") && key !== "base" && key !== "heading" && key !== "caption" && key !== "display") {
      continue;
    }
    if (isScalar(val)) {
      expandTypographyEntries(rows, seen, key, val);
      continue;
    }
    if (typeof val === "object" && val !== null && !Array.isArray(val)) {
      const obj = val as Record<string, unknown>;
      if (isTypographyStyleObject(obj)) {
        expandTypographyEntries(rows, seen, key, obj);
      } else if (fontSans && key.toLowerCase().includes("font")) {
        expandTypographyEntries(rows, seen, key, fontSans);
      } else {
        expandTypographyEntries(rows, seen, key, val);
      }
    }
  }

  return rows;
}
