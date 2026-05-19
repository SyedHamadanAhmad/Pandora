"""Unit tests for Phase 3 Step 8 — pipeline consumer lifespan wiring."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI

from app.pipeline_runtime import (
    consumer_status,
    shutdown_pipeline_runtime,
    start_pipeline_runtime,
)


class PipelineLifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_sets_broker_and_consumer_task(self) -> None:
        app = FastAPI()
        mock_connection = MagicMock()
        mock_connection.is_closed = False
        mock_connection.close = AsyncMock()
        mock_topology_channel = AsyncMock()
        mock_topology_channel.is_closed = False
        mock_publish_channel = AsyncMock()
        mock_publish_channel.is_closed = False

        async def fake_channel():
            return mock_topology_channel

        mock_connection.channel = AsyncMock(side_effect=[mock_topology_channel, mock_publish_channel])

        with (
            patch("app.pipeline_runtime.rabbitmq.connect", AsyncMock(return_value=mock_connection)),
            patch("app.pipeline_runtime.rabbitmq.declare_topology", AsyncMock()),
            patch("app.pipeline_runtime.recover_running_projects", AsyncMock()),
            patch("app.pipeline_runtime.pipeline_consumer.wire_parses_complete_callbacks"),
            patch(
                "app.pipeline_runtime.pipeline_consumer.run_forever",
                AsyncMock(side_effect=lambda *_: asyncio.sleep(3600)),
            ),
        ):
            await start_pipeline_runtime(app)

        self.assertIsNotNone(app.state.message_broker)
        self.assertIs(app.state.rabbitmq_publish_channel, mock_publish_channel)
        self.assertFalse(app.state.pipeline_consumer_task.done())
        self.assertEqual(consumer_status(app), "running")

        await shutdown_pipeline_runtime(app)
        mock_topology_channel.close.assert_awaited()
        mock_publish_channel.close.assert_awaited()
        mock_connection.close.assert_awaited()

    async def test_consumer_status_not_started_before_startup(self) -> None:
        app = FastAPI()
        self.assertEqual(consumer_status(app), "not_started")

    async def test_shutdown_cancels_consumer_task(self) -> None:
        app = FastAPI()

        async def hang_forever(*_args, **_kwargs) -> None:
            await asyncio.sleep(3600)

        mock_connection = MagicMock()
        mock_connection.is_closed = False
        mock_connection.close = AsyncMock()
        ch = AsyncMock()
        ch.is_closed = False
        mock_connection.channel = AsyncMock(return_value=ch)

        with (
            patch("app.pipeline_runtime.rabbitmq.connect", AsyncMock(return_value=mock_connection)),
            patch("app.pipeline_runtime.rabbitmq.declare_topology", AsyncMock()),
            patch("app.pipeline_runtime.recover_running_projects", AsyncMock()),
            patch("app.pipeline_runtime.pipeline_consumer.wire_parses_complete_callbacks"),
            patch("app.pipeline_runtime.pipeline_consumer.run_forever", hang_forever),
        ):
            await start_pipeline_runtime(app)
            task = app.state.pipeline_consumer_task
            await shutdown_pipeline_runtime(app)

        self.assertTrue(task.cancelled() or task.done())


if __name__ == "__main__":
    unittest.main()
