import { DEMO_SUPPRESS_ISSUES } from "../demo";
import { useCallback, useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { useToast } from "../components/Toast/ToastContext";
import { useStorybookStore } from "../stores/storybookStore";
import { handleProjectSse } from "./handleProjectSse";
import { useProjectStream } from "./useProjectStream";
import { initialPipelineRunState } from "../features/pipeline/pipelineRunState";

/**
 * SSE on storybook routes: refetch overview on live regen / completion only.
 * Suppresses toasts and overview bumps during Redis stream replay on connect.
 */
export function useStorybookProjectSse(projectId: number | null): void {
  const location = useLocation();
  const toast = useToast();
  const bumpStorybookOverview = useStorybookStore((s) => s.bumpOverviewVersion);
  const replayDoneRef = useRef(false);

  useEffect(() => {
    replayDoneRef.current = false;
  }, [projectId]);

  const onEvent = useCallback(
    (event: Record<string, unknown>) => {
      if (projectId == null) return;

      if (event.type === "sse_replay_complete") {
        replayDoneRef.current = true;
        return;
      }

      const isReplay = !replayDoneRef.current;

      const effects = handleProjectSse(
        event,
        {
          projectId,
          pathname: location.pathname,
          navigatedStorybookForProjectId: projectId,
        },
        initialPipelineRunState(),
      );

      if (effects.bumpStorybookOverview && !isReplay) {
        bumpStorybookOverview();
      }
      if (effects.toast && !isReplay && !DEMO_SUPPRESS_ISSUES) {
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
