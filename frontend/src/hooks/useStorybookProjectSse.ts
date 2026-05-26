import { useCallback } from "react";
import { useLocation } from "react-router-dom";
import { useToast } from "../components/Toast/ToastContext";
import { useStorybookStore } from "../stores/storybookStore";
import { handleProjectSse } from "./handleProjectSse";
import { useProjectStream } from "./useProjectStream";
import { initialPipelineRunState } from "../features/pipeline/pipelineRunState";

/**
 * SSE on storybook routes: refetch overview on regen / completion; toast on pipeline_complete.
 */
export function useStorybookProjectSse(projectId: number | null): void {
  const location = useLocation();
  const toast = useToast();
  const bumpStorybookOverview = useStorybookStore((s) => s.bumpOverviewVersion);

  const onEvent = useCallback(
    (event: Record<string, unknown>) => {
      if (projectId == null) return;

      const effects = handleProjectSse(
        event,
        {
          projectId,
          pathname: location.pathname,
          hasNavigatedToStorybook: true,
        },
        initialPipelineRunState(),
      );

      if (effects.bumpStorybookOverview) {
        bumpStorybookOverview();
      }
      if (effects.toast) {
        toast[effects.toast.variant](effects.toast.message);
      }
    },
    [
      projectId,
      location.pathname,
      bumpStorybookOverview,
      toast,
    ],
  );

  useProjectStream(projectId, onEvent);
}
