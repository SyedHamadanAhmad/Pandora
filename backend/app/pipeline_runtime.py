"""Pipeline RabbitMQ consumer lifecycle (Phase 3 Step 8)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI

from app import rabbitmq
from app.services import pipeline_consumer, pipeline_state
from app.services.message_broker import MessageBroker

logger = logging.getLogger(__name__)


def consumer_status(app: FastAPI) -> str:
    """``running`` | ``failed`` | ``stopped`` | ``not_started`` for health checks."""
    task = getattr(app.state, "pipeline_consumer_task", None)
    if task is None:
        return "not_started"
    if not task.done():
        return "running"
    if task.cancelled():
        return "stopped"
    if task.exception() is not None:
        return "failed"
    return "stopped"


async def start_pipeline_runtime(app: FastAPI) -> None:
    """
    Connect to RabbitMQ, declare topology, recover state, start the consumer.

    Order: topology → recovery → wire parse callbacks → consumer task.
    Uses a dedicated publish channel for API handlers (separate from consume).
    """
    connection = await rabbitmq.connect()

    topology_channel = await connection.channel()
    await rabbitmq.declare_topology(topology_channel)
    await topology_channel.close()

    publish_channel = await connection.channel()
    broker = MessageBroker(publish_channel)

    app.state.rabbitmq_connection = connection
    app.state.rabbitmq_publish_channel = publish_channel
    app.state.message_broker = broker

    callback = pipeline_consumer.make_parses_complete_callback(broker)

    async def reconcile_brief(state: pipeline_state.PipelineState) -> None:
        await pipeline_consumer.trigger_brief_work(state, broker)

    await pipeline_state.recover_running_projects(
        on_parses_complete=callback,
        reconcile_brief=reconcile_brief,
    )
    pipeline_consumer.wire_parses_complete_callbacks(broker)

    consumer_task = asyncio.create_task(
        _run_consumer_supervised(connection, broker),
        name="pipeline-consumer",
    )
    app.state.pipeline_consumer_task = consumer_task
    logger.info("pipeline consumer task started")


async def _run_consumer_supervised(
    connection,
    broker: MessageBroker,
) -> None:
    try:
        await pipeline_consumer.run_forever(connection, broker)
    except asyncio.CancelledError:
        logger.info("pipeline consumer task cancelled")
        raise
    except Exception:
        logger.exception("pipeline consumer task exited with error")
        raise


async def shutdown_pipeline_runtime(app: FastAPI) -> None:
    """Cancel consumer, close RabbitMQ channels and connection."""
    task = getattr(app.state, "pipeline_consumer_task", None)
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    publish_channel = getattr(app.state, "rabbitmq_publish_channel", None)
    if publish_channel is not None and not publish_channel.is_closed:
        await publish_channel.close()

    connection = getattr(app.state, "rabbitmq_connection", None)
    if connection is not None and not connection.is_closed:
        await connection.close()

    logger.info("pipeline runtime shut down")
