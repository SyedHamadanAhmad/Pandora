import { useEffect, useState } from "react";
import { getStorybookOverview } from "../api/storybook";
import type { StorybookOverview } from "../api/types";
import { useStorybookStore } from "../stores/storybookStore";

export function useStorybookOverview(projectId: number | null) {
  const overviewVersion = useStorybookStore((s) => s.overviewVersion);
  const setOverview = useStorybookStore((s) => s.setOverview);
  const cached = useStorybookStore((s) => s.overview);

  const [loading, setLoading] = useState(!cached);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (projectId == null || !Number.isFinite(projectId)) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    void getStorybookOverview(projectId)
      .then((data) => {
        if (!cancelled) {
          setOverview(data);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load storybook");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, overviewVersion, setOverview]);

  const overview =
    cached?.projectId === projectId ? cached : null;

  return { overview, loading, error };
}
