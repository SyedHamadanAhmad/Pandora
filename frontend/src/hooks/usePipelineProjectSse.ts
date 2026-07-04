import { DEMO_SUPPRESS_ISSUES } from "../demo";
import { useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  initialPipelineRunState,
  type PipelineRunState,
} from "../features/pipeline/pipelineRunState";
import { useToast } from "../components/Toast/ToastContext";
import { usePipelineStore } from "../stores/pipelineStore";
import { useStorybookStore } from "../stores/storybookStore";
import { handleProjectSse, type PipelineSseEffects } from "./handleProjectSse";
import { useProjectStream } from "./useProjectStream";

interface UsePipelineProjectSseOptions {
  projectId: number | null;
  setRun: React.Dispatch<React.SetStateAction<PipelineRunState>>;
}

function applyEffects(
  effects: PipelineSseEffects,
  projectId: number,
  navigate: ReturnType<typeof useNavigate>,
  markNavigatedToStorybook: (id: number) => void,
  bumpStorybookOverview: () => void,
  toast: ReturnType<typeof useToast>,
): void {
  if (effects.navigateToStorybook) {
    navigate(`/projects/${projectId}/storybook`);
  }
  if (effects.markNavigated) {
    markNavigatedToStorybook(projectId);
  }
  if (effects.bumpStorybookOverview) {
    bumpStorybookOverview();
  }
  if (effects.toast && !DEMO_SUPPRESS_ISSUES) {
    toast[effects.toast.variant](effects.toast.message);
  }
}

/**
 * Subscribes to project SSE and applies pipeline UI + storybook navigation rules.
 */
export function usePipelineProjectSse({
  projectId,
  setRun,
}: UsePipelineProjectSseOptions): void {
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const navigatedStorybookForProjectId = usePipelineStore(
    (s) => s.navigatedStorybookForProjectId,
  );
  const markNavigatedToStorybook = usePipelineStore(
    (s) => s.markNavigatedToStorybook,
  );
  const bumpStorybookOverview = useStorybookStore((s) => s.bumpOverviewVersion);

  const onEvent = useCallback(
    (event: Record<string, unknown>) => {
      if (projectId == null) return;

      let effects: PipelineSseEffects = {};

      setRun((prev) => {
        effects = handleProjectSse(
          event,
          {
            projectId,
            pathname: location.pathname,
            navigatedStorybookForProjectId,
          },
          prev,
        );
        if (effects.nextRun !== undefined) {
          return effects.nextRun;
        }
        return prev;
      });

      applyEffects(
        effects,
        projectId,
        navigate,
        markNavigatedToStorybook,
        bumpStorybookOverview,
        toast,
      );
    },
    [
      projectId,
      location.pathname,
      navigatedStorybookForProjectId,
      setRun,
      navigate,
      markNavigatedToStorybook,
      bumpStorybookOverview,
      toast,
    ],
  );

  useProjectStream(projectId, onEvent);
}

export { initialPipelineRunState };
