import type { ComponentDetail } from "../../api/types";

export function listVariantNames(
  component: ComponentDetail,
  spec: Record<string, unknown>,
): string[] {
  const fromComponent = component.variants
    ?.map((v) => {
      if (v && typeof v === "object" && "name" in v) {
        const n = (v as { name?: unknown }).name;
        return typeof n === "string" && n.trim() ? n.trim() : null;
      }
      return null;
    })
    .filter((x): x is string => Boolean(x));

  if (fromComponent && fromComponent.length > 0) {
    return fromComponent;
  }

  const fromSpec = spec.variants;
  if (Array.isArray(fromSpec)) {
    const names = fromSpec
      .map((x) => (typeof x === "string" && x.trim() ? x.trim() : null))
      .filter((x): x is string => Boolean(x));
    if (names.length > 0) return names;
  }

  return ["default"];
}

/**
 * Merges spec defaults, persisted component.props, and variant-specific props
 * for the live Sandpack preview.
 */
export function computeMergedProps(
  component: ComponentDetail,
  spec: Record<string, unknown>,
  variantName: string,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};

  const specProps = spec.props;
  if (specProps && typeof specProps === "object" && !Array.isArray(specProps)) {
    for (const [k, v] of Object.entries(specProps as Record<string, unknown>)) {
      if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
        out[k] = v;
      }
    }
  }

  if (
    component.props &&
    typeof component.props === "object" &&
    !Array.isArray(component.props)
  ) {
    Object.assign(out, component.props as Record<string, unknown>);
  }

  const vars = component.variants;
  if (vars && variantName) {
    const match = vars.find((item) => {
      if (!item || typeof item !== "object") return false;
      const n = (item as { name?: unknown }).name;
      return String(n ?? "") === variantName;
    });
    if (match && typeof match === "object" && "props" in match) {
      const vp = (match as { props?: unknown }).props;
      if (vp && typeof vp === "object" && !Array.isArray(vp)) {
        Object.assign(out, vp as Record<string, unknown>);
      }
    }
  }

  // Most generated components use a `variant` prop, but the API often only
  // stores variant *names* on each row — not per-variant `props` blobs. Without
  // this, `component.props.variant` (e.g. "primary") would never change when the
  // user picks another option in the Props panel, so Sandpack would look "stuck".
  const variantOptions = listVariantNames(component, spec);
  if (variantOptions.length > 1) {
    out.variant = variantName;
  } else if ("variant" in out) {
    out.variant = variantName;
  }

  return out;
}

export function sampleForPropKey(key: string): string {
  const lower = key.toLowerCase();
  if (lower.includes("title")) return "Preview title";
  if (lower.includes("label")) return "Preview label";
  if (lower.includes("text")) return "Preview text";
  if (lower.includes("placeholder")) return "Type here…";
  if (lower.includes("subtitle")) return "Supporting line for the preview.";
  if (lower === "children") return "Preview body content.";
  return `Sample ${key}`;
}
