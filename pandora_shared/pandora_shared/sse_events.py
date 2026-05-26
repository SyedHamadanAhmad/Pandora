"""Canonical SSE event ``type`` values for project streams (Phase 5).

Frontend subscribes via ``GET /api/projects/{project_id}/stream``.
Wire format: ``event: message`` with JSON body including ``type``.

Note: completion is ``pipeline_complete`` (not ``project_completed``).
"""

from __future__ import annotations

# Pipeline lifecycle
DESIGN_BRIEF_READY = "design_brief_ready"
SCHEMA_READY = "schema_ready"
PIPELINE_COMPLETE = "pipeline_complete"
VERIFICATION_RUNNING = "verification_running"
REVISION_RUNNING = "revision_running"

# Per-component outcomes (from workers → consumer)
COMPONENT_VALIDATED = "component_validated"
COMPONENT_FAILED = "component_failed"

# Storybook user actions (from REST handlers)
TOKEN_REGENERATION_STARTED = "token_regeneration_started"
COMPONENT_REVISION_STARTED = "component_revision_started"

# Optional v2
COMPONENTS_READY = "components_ready"

PIPELINE_SSE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        DESIGN_BRIEF_READY,
        SCHEMA_READY,
        PIPELINE_COMPLETE,
        VERIFICATION_RUNNING,
        REVISION_RUNNING,
        COMPONENT_VALIDATED,
        COMPONENT_FAILED,
        COMPONENTS_READY,
    }
)

STORYBOOK_SSE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        TOKEN_REGENERATION_STARTED,
        COMPONENT_REVISION_STARTED,
    }
)

ALL_SSE_EVENT_TYPES: frozenset[str] = PIPELINE_SSE_EVENT_TYPES | STORYBOOK_SSE_EVENT_TYPES
