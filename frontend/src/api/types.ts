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

/** Rough progress budget slices (percent of top bar). */
export const PIPELINE_PROGRESS = {
  briefReady: 10,
} as const;
