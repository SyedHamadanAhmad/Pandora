"""Unit tests for storybook component revise (Phase 4)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.services.storybook_revise import revise_component
from pandora_shared.enums import ComponentStatus


class _FakeComponent:
    def __init__(
        self,
        *,
        component_id: int = 1,
        project_id: int = 10,
        status: ComponentStatus = ComponentStatus.validated,
    ) -> None:
        self.id = component_id
        self.project_id = project_id
        self.spec_index = 0
        self.name = "Button"
        self.status = status
        self.retry_count = 0
        self.revision_round = 0
        self.revision_instruction: str | None = None


class _FakeSchema:
    design_tokens = {"primary": "#f97316"}
    global_config = {"theme": "light"}
    component_specs = [{"name": "Button", "type": "button"}]


class _FakeProject:
    def __init__(self, project_id: int = 10) -> None:
        self.id = project_id


class ReviseComponentServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_revise_enqueues_and_emits_sse(self) -> None:
        component = _FakeComponent()
        project = _FakeProject()
        session = AsyncMock()
        session.get = AsyncMock(return_value=component)
        pipeline_id = 42

        with (
            patch(
                "app.services.storybook_revise.assert_storybook_idle",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.storybook_revise.require_design_schema",
                new_callable=AsyncMock,
                return_value=_FakeSchema(),
            ),
            patch(
                "app.services.storybook_revise.resolve_latest_pipeline_run_id",
                new_callable=AsyncMock,
                return_value=pipeline_id,
            ),
            patch(
                "app.services.storybook_revise.enqueue_outbox",
                new_callable=AsyncMock,
                return_value=True,
            ) as enqueue_outbox,
            patch("app.services.storybook_revise.sse_service.emit") as emit_sse,
        ):
            result = await revise_component(
                session,
                project,  # type: ignore[arg-type]
                component.id,
                "Use white text on primary button",
            )

        self.assertEqual(result.component_id, 1)
        self.assertEqual(result.status, ComponentStatus.generating)
        self.assertEqual(component.status, ComponentStatus.generating)
        self.assertEqual(component.revision_instruction, "Use white text on primary button")
        self.assertEqual(component.revision_round, 1)
        enqueue_outbox.assert_awaited_once()
        session.commit.assert_awaited_once()
        emit_sse.assert_called_once()
        from pandora_shared.sse_events import COMPONENT_REVISION_STARTED

        self.assertEqual(emit_sse.call_args[0][1]["type"], COMPONENT_REVISION_STARTED)

    async def test_revise_rejects_when_component_generating(self) -> None:
        component = _FakeComponent(status=ComponentStatus.generating)
        session = AsyncMock()
        session.get = AsyncMock(return_value=component)

        with patch(
            "app.services.storybook_revise.assert_storybook_idle",
            new_callable=AsyncMock,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await revise_component(
                    session,
                    _FakeProject(),  # type: ignore[arg-type]
                    1,
                    "fix contrast",
                )
        self.assertEqual(ctx.exception.status_code, 409)

    async def test_revise_rejects_empty_message(self) -> None:
        with patch(
            "app.services.storybook_revise.assert_storybook_idle",
            new_callable=AsyncMock,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await revise_component(
                    AsyncMock(),
                    _FakeProject(),  # type: ignore[arg-type]
                    1,
                    "   ",
                )
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
