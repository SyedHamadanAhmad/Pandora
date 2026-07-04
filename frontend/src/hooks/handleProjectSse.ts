import type { PipelineRunState } from "../features/pipeline/pipelineRunState";
import { reducePipelineSse } from "../features/pipeline/pipelineRunState";
import type { ComponentsReadySource } from "../api/types";

export interface PipelineSseContext {
  projectId: number;
  pathname: string;
  /** Project id already auto-navigated to storybook; null if none. */
  navigatedStorybookForProjectId: number | null;
}

export interface PipelineSseEffects {
  /** Apply pipeline run UI state (brief, schema, component rows). */
  nextRun?: PipelineRunState;
  /** Navigate to storybook overview for this project. */
  navigateToStorybook?: boolean;
  /** Mark navigation dedupe flag for this project. */
  markNavigated?: boolean;
  /** Bump storybook overview refetch counter. */
  bumpStorybookOverview?: boolean;
  /** Toast after pipeline_complete when already on storybook. */
  toast?: { message: string; variant: "success" | "warning" };
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

function hasNavigatedForProject(ctx: PipelineSseContext): boolean {
  return ctx.navigatedStorybookForProjectId === ctx.projectId;
}

function shouldNavigateOnComponentsReady(
  source: ComponentsReadySource | string | undefined,
  ctx: PipelineSseContext,
): boolean {
  if (hasNavigatedForProject(ctx)) return false;
  return source === "pipeline" || source === "pipeline_complete";
}

function isStorybookUserAction(event: Record<string, unknown>): boolean {
  const source = event.source as string | undefined;
  const revisionRound =
    event.revisionRound != null ? Number(event.revisionRound) : 0;
  return (
    source === "storybook_revise" ||
    source === "storybook_regen" ||
    revisionRound > 0
  );
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
      if (shouldNavigateOnComponentsReady(source, ctx)) {
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
      } else if (!hasNavigatedForProject(ctx)) {
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
        if (isStorybookUserAction(event)) {
          effects.toast = {
            message: "Component updated successfully",
            variant: "success",
          };
        }
      }
      break;
    }

    case "component_failed": {
      if (isOnStorybookRoute(ctx.pathname, ctx.projectId)) {
        effects.bumpStorybookOverview = true;
        if (isStorybookUserAction(event)) {
          effects.toast = {
            message:
              "Component refinement failed — check the error and try again",
            variant: "warning",
          };
        }
      }
      break;
    }

    default:
      break;
  }

  return effects;
}
