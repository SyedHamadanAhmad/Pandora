"""SSE fan-out for pipeline progress (Phase 3 Step 6 — stub until stream route exists)."""

from __future__ import annotations

from typing import Any


def emit(project_id: int, event: dict[str, Any]) -> None:
    """Push a project-scoped event to connected SSE clients (no-op in Step 5 stub)."""
    _ = project_id, event
