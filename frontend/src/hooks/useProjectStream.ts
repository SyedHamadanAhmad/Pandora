import { useEffect, useRef } from "react";

export type SseHandler = (event: Record<string, unknown>) => void;

/**
 * Subscribe to project SSE (`GET /api/projects/:id/stream`).
 * Uses cookies for auth (same-origin).
 */
export function useProjectStream(
  projectId: number | null,
  onEvent: SseHandler,
): void {
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (projectId == null) return;

    const url = `/api/projects/${projectId}/stream`;
    const es = new EventSource(url, { withCredentials: true });

    es.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as Record<string, unknown>;
        if (msg.lastEventId) {
          data.sseId = msg.lastEventId;
        }
        onEventRef.current(data);
      } catch {
        /* ignore malformed frames */
      }
    };

    es.onerror = () => {
      /* browser reconnects automatically */
    };

    return () => {
      es.close();
    };
  }, [projectId]);
}
