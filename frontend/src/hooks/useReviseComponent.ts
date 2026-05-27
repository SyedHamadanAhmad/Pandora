import { useCallback, useState } from "react";
import { reviseComponent } from "../api/storybook";
import { useToast } from "../components/Toast/ToastContext";
import { useStorybookStore } from "../stores/storybookStore";
import { validateRefineMessage } from "../utils/refineMessage";

/**
 * Submit per-component revise requests and track in-flight component ids.
 */
export function useReviseComponent(projectId: number | null) {
  const toast = useToast();
  const bumpOverview = useStorybookStore((s) => s.bumpOverviewVersion);
  const [pendingIds, setPendingIds] = useState<Set<number>>(() => new Set());

  const revise = useCallback(
    async (componentId: number, message: string): Promise<boolean> => {
      if (projectId == null || !Number.isFinite(projectId)) {
        return false;
      }

      const validationError = validateRefineMessage(message);
      if (validationError) {
        toast.error(validationError);
        return false;
      }

      setPendingIds((prev) => new Set(prev).add(componentId));
      try {
        await reviseComponent(projectId, componentId, message.trim());
        toast.success("Refining component…");
        bumpOverview();
        return true;
      } catch (err) {
        const detail =
          err instanceof Error ? err.message : "Could not start refinement";
        toast.error(detail);
        return false;
      } finally {
        setPendingIds((prev) => {
          const next = new Set(prev);
          next.delete(componentId);
          return next;
        });
      }
    },
    [projectId, toast, bumpOverview],
  );

  const isRevisePending = useCallback(
    (componentId: number) => pendingIds.has(componentId),
    [pendingIds],
  );

  return { revise, isRevisePending };
}
