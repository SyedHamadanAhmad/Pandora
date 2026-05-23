"""Unit tests for storybook SSE emit payloads."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.project import Project
from app.services.storybook_tokens import apply_design_tokens
from pandora_shared.enums import ProjectStatus
from pandora_shared.sse_events import TOKEN_REGENERATION_STARTED


class StorybookSseEmitTests(unittest.IsolatedAsyncioTestCase):
    async def test_token_apply_emits_sse_type(self) -> None:
        project = Project(user_id=1, name="p", status=ProjectStatus.completed)
        project.id = 99

        session = AsyncMock()
        schema = MagicMock()
        schema.design_tokens = {"primary": "#f97316"}
        schema.global_config = {}

        with (
            patch(
                "app.services.storybook_tokens.assert_storybook_idle",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.storybook_tokens.require_design_schema",
                new_callable=AsyncMock,
                return_value=schema,
            ),
            patch(
                "app.services.storybook_tokens._require_non_empty_patch",
                return_value={"primary": "#ea580c"},
            ),
            patch(
                "app.services.storybook_tokens.merge_design_tokens",
                return_value={"primary": "#ea580c", "on_primary": "#fff"},
            ),
            patch(
                "app.services.storybook_tokens.fanout_token_regeneration",
                new_callable=AsyncMock,
                return_value=2,
            ),
            patch("app.services.storybook_tokens.sse_service.emit") as emit_sse,
        ):
            await apply_design_tokens(
                session,
                project,
                {"primary": "#ea580c"},
                regenerate_components=True,
            )

        event = emit_sse.call_args[0][1]
        self.assertEqual(event["type"], TOKEN_REGENERATION_STARTED)
        self.assertEqual(event["projectId"], 99)
        self.assertEqual(event["total"], 2)


if __name__ == "__main__":
    unittest.main()
