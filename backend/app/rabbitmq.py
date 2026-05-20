"""RabbitMQ connection and queue topology declaration."""

from __future__ import annotations

import asyncio
import logging
import os

import aio_pika
from aio_pika import RobustChannel, RobustConnection

from app.config import settings
from pandora_shared.queues import ALL_QUEUES

logger = logging.getLogger(__name__)


async def connect(
    *,
    max_attempts: int | None = None,
    delay_seconds: float = 2.0,
) -> RobustConnection:
    """Connect with retries so API startup survives compose RabbitMQ readiness races."""
    attempts = max_attempts
    if attempts is None:
        raw = os.environ.get("RABBITMQ_CONNECT_ATTEMPTS", "30").strip()
        try:
            attempts = max(1, int(raw))
        except ValueError:
            attempts = 30

    url = settings.rabbitmq_url
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await aio_pika.connect_robust(url)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "RabbitMQ connect failed (%s/%s): %s",
                attempt,
                attempts,
                exc,
            )
            if attempt < attempts:
                await asyncio.sleep(delay_seconds)

    assert last_error is not None
    raise last_error


async def declare_topology(channel: RobustChannel) -> None:
    """Declare all pipeline queues and their dead-letter queues (idempotent)."""
    for queue_name in ALL_QUEUES:
        dlq_name = f"{queue_name}.dlq"
        await channel.declare_queue(dlq_name, durable=True)
        await channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": dlq_name,
            },
        )
