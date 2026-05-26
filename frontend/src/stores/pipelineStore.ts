import { create } from "zustand";

interface PipelineStore {
  /** Avoid duplicate navigate on components_ready + pipeline_complete */
  hasNavigatedToStorybook: boolean;
  markNavigatedToStorybook: () => void;
  reset: () => void;
}

export const usePipelineStore = create<PipelineStore>((set) => ({
  hasNavigatedToStorybook: false,
  markNavigatedToStorybook: () => set({ hasNavigatedToStorybook: true }),
  reset: () => set({ hasNavigatedToStorybook: false }),
}));
