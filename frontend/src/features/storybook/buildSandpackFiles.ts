import type { SandpackFiles } from "@codesandbox/sandpack-react";
import { designTokensToCss } from "../../utils/designTokensToCss";
import { extractComponentExportName } from "../../utils/extractComponentExportName";

function tsxReferencesCssImport(tsx: string): boolean {
  return /\.css['"]/.test(tsx);
}

function withStylesImport(tsx: string, hasCss: boolean): string {
  if (!hasCss || tsxReferencesCssImport(tsx)) return tsx;
  return `import "./styles.css";\n${tsx}`;
}

function serializePropLiteral(key: string, val: unknown): string | null {
  if (val === undefined) return null;
  if (typeof val === "string") return `${JSON.stringify(key)}: ${JSON.stringify(val)}`;
  if (typeof val === "number" || typeof val === "boolean") {
    return `${JSON.stringify(key)}: ${String(val)}`;
  }
  if (val === null) return `${JSON.stringify(key)}: null`;
  if (Array.isArray(val) || (typeof val === "object" && val !== null)) {
    try {
      return `${JSON.stringify(key)}: ${JSON.stringify(val)}`;
    } catch {
      return null;
    }
  }
  return null;
}

function callbackStubsFromTsx(tsx: string, propKeys: Set<string>): string[] {
  const stubs: string[] = [];
  const candidates = ["onClick", "onChange", "onSubmit", "onClose", "onOpenChange"] as const;
  for (const name of candidates) {
    const re = new RegExp(`\\b${name}\\s*\\??\\s*:`);
    if (re.test(tsx) && !propKeys.has(name)) {
      stubs.push(`${JSON.stringify(name)}: () => {}`);
    }
  }
  return stubs;
}

export function buildSandpackFiles(options: {
  componentName: string;
  tsxCode: string;
  cssCode: string | null | undefined;
  designTokens: Record<string, unknown>;
  previewProps: Record<string, unknown>;
  suppressPreviewErrors?: boolean;
}): SandpackFiles {
  const exportName = extractComponentExportName(options.tsxCode, options.componentName);
  const hasCss = Boolean(options.cssCode?.trim());
  const componentBody = withStylesImport(options.tsxCode, hasCss);

  const propKeys = new Set(Object.keys(options.previewProps));
  const literalLines = Object.entries(options.previewProps)
    .map(([k, v]) => serializePropLiteral(k, v))
    .filter((x): x is string => x != null);
  literalLines.push(...callbackStubsFromTsx(options.tsxCode, propKeys));

  const propsObjectSrc =
    literalLines.length > 0 ? `${literalLines.join(",\n  ")},\n` : "";

  const previewBody = `    <div className="sandpack-preview-root" style={{ padding: 24 }}>
      <${exportName} {...previewProps} />
    </div>`;

  const appCode = options.suppressPreviewErrors
    ? `import "./tokens.css";
import React from "react";
import { ${exportName} } from "./Component";

const previewProps: Record<string, unknown> = {
  ${propsObjectSrc}};

class PreviewErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch() {}

  render() {
    if (this.state.hasError) {
      return <div className="sandpack-preview-root" style={{ padding: 24 }} />;
    }
    return this.props.children;
  }
}

export default function App() {
  return (
    <PreviewErrorBoundary>
${previewBody}
    </PreviewErrorBoundary>
  );
}
`
    : `import "./tokens.css";
import { ${exportName} } from "./Component";

const previewProps: Record<string, unknown> = {
  ${propsObjectSrc}};

export default function App() {
  return (
${previewBody}
  );
}
`;

  const files: SandpackFiles = {
    "/tokens.css": {
      code: designTokensToCss(options.designTokens),
    },
    "/Component.tsx": {
      code: componentBody,
    },
    "/App.tsx": {
      code: appCode,
    },
  };

  if (hasCss) {
    files["/styles.css"] = { code: options.cssCode!.trim() };
  }

  return files;
}
