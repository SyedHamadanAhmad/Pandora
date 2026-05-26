import { create } from "zustand";
import type { StorybookOverview } from "../api/types";

interface StorybookStore {
  overview: StorybookOverview | null;
  overviewVersion: number;
  setOverview: (overview: StorybookOverview | null) => void;
  bumpOverviewVersion: () => void;
  reset: () => void;
}

export const useStorybookStore = create<StorybookStore>((set) => ({
  overview: null,
  overviewVersion: 0,
  setOverview: (overview) => set({ overview }),
  bumpOverviewVersion: () =>
    set((s) => ({ overviewVersion: s.overviewVersion + 1 })),
  reset: () => set({ overview: null, overviewVersion: 0 }),
}));
