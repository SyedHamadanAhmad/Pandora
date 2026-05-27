import type { PipelineRunState } from "../features/pipeline/pipelineRunState";
import { reducePipelineSse } from "../features/pipeline/pipelineRunState";
import type { ComponentsReadySource } from "../api/types";

export interface PipelineSseContext {
  projectId: number;
  pathname: string;
  hasNavigatedToStorybook: boolean;
}

export interface PipelineSseEffects {
  /** Apply pipeline run UI state (brief, schema, component rows). */
  nextRun?: PipelineRunState;
  /** Navigate to storybook overview for this project. */
  navigateToStorybook?: boolean;
  /** Mark navigation dedupe flag. */
  markNavigated?: boolean;
  /** Bump storybook overview refetch counter. */
  bumpStorybookOverview?: boolean;
  /** Toast after pipeline_complete when already on storybook. */
  toast?: { message: string; variant: "success" };
}

const PIPELINE_RUN_EVENT_TYPES = new Set([
  "design_brief_ready",
  "schema_ready",
  "component_validated",
  "component_failed",
]);

function isOnStorybookRoute(pathname: string, projectId: number): boolean {
  return pathname.includes(`/projects/${projectId}/storybook`);
}

function shouldNavigateOnComponentsReady(
  source: ComponentsReadySource | string | undefined,
  hasNavigated: boolean,
): boolean {
  if (hasNavigated) return false;
  return source === "pipeline" || source === "pipeline_complete";
}

/**
 * Map one SSE event to pipeline UI updates and navigation side effects.
 */
export function handleProjectSse(
  event: Record<string, unknown>,
  ctx: PipelineSseContext,
  prevRun: PipelineRunState,
): PipelineSseEffects {
  const effects: PipelineSseEffects = {};

  if (PIPELINE_RUN_EVENT_TYPES.has(String(event.type))) {
    effects.nextRun = reducePipelineSse(prevRun, event);
  }

  switch (event.type) {
    case "components_ready": {
      const source = event.source as ComponentsReadySource | string | undefined;
      if (shouldNavigateOnComponentsReady(source, ctx.hasNavigatedToStorybook)) {
        effects.navigateToStorybook = true;
        effects.markNavigated = true;
      }
      if (source === "storybook_regen") {
        effects.bumpStorybookOverview = true;
      }
      if (
        isOnStorybookRoute(ctx.pathname, ctx.projectId) &&
        (source === "pipeline_complete" || source === "storybook_regen")
      ) {
        effects.bumpStorybookOverview = true;
      }
      break;
    }

    case "pipeline_complete": {
      if (isOnStorybookRoute(ctx.pathname, ctx.projectId)) {
        effects.toast = { message: "Pipeline finished", variant: "success" };
        effects.bumpStorybookOverview = true;
      } else if (!ctx.hasNavigatedToStorybook) {
        effects.navigateToStorybook = true;
        effects.markNavigated = true;
      }
      break;
    }

    case "component_revision_started": {
      if (isOnStorybookRoute(ctx.pathname, ctx.projectId)) {
        effects.bumpStorybookOverview = true;
      }
      break;
    }

    case "component_validated": {
      if (isOnStorybookRoute(ctx.pathname, ctx.projectId)) {
        effects.bumpStorybookOverview = true;
        effects.toast = {
          message: "Component refined successfully",
          variant: "success",
        };
      }
      break;
    }

    case "component_failed": {
      if (isOnStorybookRoute(ctx.pathname, ctx.projectId)) {
        effects.bumpStorybookOverview = true;
        effects.toast = {
          message: "Component refinement failed — check the error and try again",
          variant: "warning",
        };
      }
      break;
    }

    default:
      break;
  }

  return effects;
}
