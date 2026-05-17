"""Unit tests for pipeline trigger service."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.services import pipeline_state
from app.services.pipeline_service import trigger_pipeline_run
from pandora_shared.enums import ProjectStatus
from pandora_shared.queues import PARSE_TEXT


class PipelineServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        pipeline_state.pipeline_states.clear()

    def tearDown(self) -> None:
        pipeline_state.pipeline_states.clear()

    async def test_trigger_sets_running_and_publishes_parse_jobs(self) -> None:
        project = MagicMock()
        project.id = 1
        project.status = ProjectStatus.pending

        message = MagicMock()
        message.content = "Modern dashboard"
        message.input_image_urls = None
        message.input_urls = None
        message.pipeline_id = None

        db = AsyncMock()
        broker = AsyncMock()
        published: list[str] = []

        async def capture_publish(queue_name: str, envelope) -> None:
            published.append(queue_name)

        broker.publish.side_effect = capture_publish

        with (
            patch(
                "app.services.pipeline_service.copy_thread_images_to_pipeline",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.pipeline_service.pipeline_state.schedule_parse_timeouts",
            ),
        ):
            result = await trigger_pipeline_run(db, broker, project, message)

        self.assertEqual(result.status, ProjectStatus.running)
        self.assertIsInstance(result.pipeline_id, UUID)
        self.assertEqual(message.pipeline_id, result.pipeline_id)
        self.assertEqual(project.status, ProjectStatus.running)
        db.commit.assert_awaited()
        broker.publish.assert_awaited_once()
        self.assertEqual(published, [PARSE_TEXT])
        self.assertIn(result.pipeline_id, pipeline_state.pipeline_states)

        for task in pipeline_state.get_state(result.pipeline_id)._timeout_tasks:
            task.cancel()


if __name__ == "__main__":
    unittest.main()
