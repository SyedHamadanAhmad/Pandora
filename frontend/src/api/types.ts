export type ProjectStatus = "pending" | "running" | "completed" | "failed";

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

/** Rough progress budget slices (percent of top bar). */
export const PIPELINE_PROGRESS = {
  briefReady: 10,
  schemaReady: 25,
  componentsEnd: 90,
} as const;
