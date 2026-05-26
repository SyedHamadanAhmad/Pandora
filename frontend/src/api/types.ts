export type ProjectStatus = "pending" | "running" | "completed" | "failed";

export type ComponentStatus =
  | "pending"
  | "generating"
  | "validating"
  | "validated"
  | "failed"
  | "revised";

export interface Project {
  id: number;
  name: string;
  status: ProjectStatus;
  createdAt: string;
  updatedAt: string;
}

/** SSE payload for `design_brief_ready` (camelCase from backend). */
export interface DesignBriefReadyEvent {
  type: "design_brief_ready";
  projectId: number;
  pipelineId: string;
  colorTokens: Record<string, string>;
  typographyScale: Record<string, string | number>;
  spacingSystem: Record<string, unknown>;
  tone?: string | null;
  componentList: string[];
  inputGaps: string[];
}

/** SSE payload for `schema_ready`. */
export interface SchemaReadyEvent {
  type: "schema_ready";
  projectId: number;
  pipelineId: string;
  componentCount: number;
  components: string[];
}

export interface ComponentValidatedEvent {
  type: "component_validated";
  projectId: number;
  pipelineId: string;
  componentId: string;
  componentName: string;
}

export interface ComponentFailedEvent {
  type: "component_failed";
  projectId: number;
  pipelineId: string;
  componentId: string;
  componentName: string;
  error?: string;
}

export type ComponentsReadySource =
  | "pipeline"
  | "storybook_regen"
  | "pipeline_complete";

export interface ComponentsReadyEvent {
  type: "components_ready";
  projectId: number;
  pipelineId: string;
  componentCount: number;
  revisionRound: number;
  source: ComponentsReadySource;
}

export interface PipelineCompleteEvent {
  type: "pipeline_complete";
  projectId: number;
  pipelineId: string;
}

/** Rough progress budget slices (percent of top bar). */
export const PIPELINE_PROGRESS = {
  briefReady: 10,
  schemaReady: 25,
  componentsEnd: 90,
} as const;

/* —— Storybook REST (GET /storybook, etc.) —— */

export interface SemanticTokenPair {
  background: string;
  foreground: string;
}

export interface TokenSchema {
  editable: string[];
  semanticPairs: SemanticTokenPair[];
}

export interface ComponentSpecSummary {
  name: string;
  type?: string | null;
  variants: string[];
  props?: Record<string, unknown> | unknown[] | null;
}

export interface StorybookComponentSummary {
  id: number;
  name: string;
  status: ComponentStatus;
  specIndex: number;
  variants?: Record<string, unknown>[] | null;
  props?: Record<string, unknown> | unknown[] | null;
  previewAvailable: boolean;
  tsxPreview?: string | null;
  cssPreview?: string | null;
  errorReason?: string | null;
}

export interface StorybookSummary {
  total: number;
  validated: number;
  failed: number;
  generating: number;
  validating: number;
  revised: number;
}

export interface StorybookOverview {
  projectId: number;
  projectStatus: ProjectStatus;
  designTokens: Record<string, unknown>;
  tokenSchema: TokenSchema;
  globalConfig: Record<string, unknown>;
  componentSpecs: ComponentSpecSummary[];
  components: StorybookComponentSummary[];
  summary: StorybookSummary;
}

export interface ComponentDetail {
  id: number;
  specIndex: number;
  name: string;
  status: ComponentStatus;
  tsxCode?: string | null;
  cssCode?: string | null;
  errorReason?: string | null;
  retryCount: number;
  revisionRound: number;
  props?: Record<string, unknown> | unknown[] | null;
  variants?: Record<string, unknown>[] | null;
  revisionInstruction?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ComponentDetailResponse {
  projectId: number;
  component: ComponentDetail;
  spec: Record<string, unknown>;
  designTokens: Record<string, unknown>;
  globalConfig: Record<string, unknown>;
}
