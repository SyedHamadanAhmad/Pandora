import { create } from "zustand";

interface PipelineStore {
  /** Last project id auto-navigated to storybook; null if none. */
  navigatedStorybookForProjectId: number | null;
  markNavigatedToStorybook: (projectId: number) => void;
  reset: () => void;
}

export const usePipelineStore = create<PipelineStore>((set) => ({
  navigatedStorybookForProjectId: null,
  markNavigatedToStorybook: (projectId) =>
    set({ navigatedStorybookForProjectId: projectId }),
  reset: () => set({ navigatedStorybookForProjectId: null }),
}));
