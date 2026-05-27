import { useMemo } from "react";
import { Sandpack } from "@codesandbox/sandpack-react";
import { buildSandpackFiles } from "./buildSandpackFiles";
import "./ComponentSandpack.css";

interface ComponentSandpackProps {
  componentName: string;
  tsxCode: string;
  cssCode?: string | null;
  designTokens: Record<string, unknown>;
  previewProps: Record<string, unknown>;
  sandpackKey: string;
}

export function ComponentSandpack({
  componentName,
  tsxCode,
  cssCode,
  designTokens,
  previewProps,
  sandpackKey,
}: ComponentSandpackProps) {
  const files = useMemo(
    () =>
      buildSandpackFiles({
        componentName,
        tsxCode,
        cssCode,
        designTokens,
        previewProps,
      }),
    [componentName, tsxCode, cssCode, designTokens, previewProps],
  );

  return (
    <div className="component-sandpack" key={sandpackKey}>
      <Sandpack
        template="react-ts"
        theme="light"
        files={files}
        options={{
          layout: "preview",
          showConsole: false,
          showConsoleButton: false,
          showNavigator: false,
          showTabs: false,
          showLineNumbers: false,
        }}
      />
    </div>
  );
}
