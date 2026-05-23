"""Unit tests for pipeline trigger service."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import pipeline_state
from app.services.pipeline_service import trigger_pipeline_run
from pandora_shared.enums import ProjectStatus
from pandora_shared.queues import PARSE_TEXT

_PIPELINE_RUN_ID = 99


class PipelineServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_trigger_sets_running_and_enqueues_parse_jobs(self) -> None:
        project = MagicMock()
        project.id = 1
        project.status = ProjectStatus.pending

        message = MagicMock()
        message.content = "Modern dashboard"
        message.input_image_urls = None
        message.input_urls = None
        message.id = 10
        message.pipeline_run_id = None

        db = AsyncMock()
        enqueued: list[str] = []

        async def capture_enqueue(session, queue_name, envelope, **kwargs) -> bool:
            enqueued.append(queue_name)
            return True

        mock_state = pipeline_state.PipelineState(
            project_id=1,
            pipeline_id=_PIPELINE_RUN_ID,
            parse_expected=1,
            parse_pending={"text"},
        )

        with (
            patch(
                "app.services.pipeline_service.copy_thread_images_to_pipeline",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.pipeline_service.pipeline_state.init_state_from_thread",
                new_callable=AsyncMock,
                return_value=mock_state,
            ),
            patch(
                "app.services.pipeline_service.pipeline_state.schedule_parse_timeouts",
            ),
            patch(
                "app.services.pipeline_service.enqueue_outbox",
                side_effect=capture_enqueue,
            ),
        ):
            result = await trigger_pipeline_run(db, project, message)

        self.assertEqual(result.status, ProjectStatus.running)
        self.assertEqual(result.pipeline_id, _PIPELINE_RUN_ID)
        self.assertEqual(project.status, ProjectStatus.running)
        db.commit.assert_awaited()
        self.assertEqual(enqueued, [PARSE_TEXT])
        self.assertIn(result.pipeline_id, pipeline_state.pipeline_states)


if __name__ == "__main__":
    unittest.main()
