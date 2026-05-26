import type {
  ComponentFailedEvent,
  ComponentValidatedEvent,
  DesignBriefReadyEvent,
  SchemaReadyEvent,
} from "../../api/types";
import { PIPELINE_PROGRESS } from "../../api/types";

export type ComponentRowStatus =
  | "pending"
  | "building"
  | "validated"
  | "failed";

export interface ComponentRow {
  name: string;
  status: ComponentRowStatus;
  error?: string;
}

export interface PipelineRunState {
  brief: DesignBriefReadyEvent | null;
  schema: SchemaReadyEvent | null;
  components: ComponentRow[];
  progress: number;
  progressPulse: boolean;
  generationStarted: boolean;
}

export const initialPipelineRunState = (): PipelineRunState => ({
  brief: null,
  schema: null,
  components: [],
  progress: 0,
  progressPulse: false,
  generationStarted: false,
});

function componentProgressPercent(
  components: ComponentRow[],
  schemaReady: boolean,
): number {
  if (!schemaReady || components.length === 0) {
    return PIPELINE_PROGRESS.schemaReady;
  }
  const done = components.filter(
    (c) => c.status === "validated" || c.status === "failed",
  ).length;
  const span = PIPELINE_PROGRESS.componentsEnd - PIPELINE_PROGRESS.schemaReady;
  return PIPELINE_PROGRESS.schemaReady + Math.round((done / components.length) * span);
}

function promotePendingToBuilding(components: ComponentRow[]): ComponentRow[] {
  return components.map((row) =>
    row.status === "pending" ? { ...row, status: "building" as const } : row,
  );
}

function updateComponentRow(
  components: ComponentRow[],
  name: string,
  update: Partial<ComponentRow>,
): ComponentRow[] {
  const key = name.toLowerCase();
  return components.map((row) =>
    row.name.toLowerCase() === key ? { ...row, ...update } : row,
  );
}

export function reducePipelineSse(
  state: PipelineRunState,
  event: Record<string, unknown>,
): PipelineRunState {
  switch (event.type) {
    case "design_brief_ready": {
      const brief = event as DesignBriefReadyEvent;
      return {
        ...state,
        brief,
        progress: PIPELINE_PROGRESS.briefReady,
        progressPulse: false,
      };
    }

    case "schema_ready": {
      const schema = event as SchemaReadyEvent;
      const names =
        schema.components.length > 0
          ? schema.components
          : Array.from({ length: schema.componentCount }, (_, i) => `component-${i}`);
      const components: ComponentRow[] = names.map((name) => ({
        name,
        status: "pending",
      }));
      return {
        ...state,
        schema,
        components,
        progress: PIPELINE_PROGRESS.schemaReady,
        progressPulse: false,
        generationStarted: false,
      };
    }

    case "component_validated": {
      const payload = event as ComponentValidatedEvent;
      let components = updateComponentRow(state.components, payload.componentName, {
        status: "validated",
        error: undefined,
      });
      if (!state.generationStarted) {
        components = promotePendingToBuilding(components);
      }
      return {
        ...state,
        components,
        generationStarted: true,
        progress: componentProgressPercent(components, state.schema != null),
      };
    }

    case "component_failed": {
      const payload = event as ComponentFailedEvent;
      let components = updateComponentRow(state.components, payload.componentName, {
        status: "failed",
        error: payload.error,
      });
      if (!state.generationStarted) {
        components = promotePendingToBuilding(components);
      }
      return {
        ...state,
        components,
        generationStarted: true,
        progress: componentProgressPercent(components, state.schema != null),
      };
    }

    default:
      return state;
  }
}
