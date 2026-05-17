"""RabbitMQ connection and queue topology declaration."""

import aio_pika
from aio_pika import RobustChannel, RobustConnection

from app.config import settings
from pandora_shared.queues import ALL_QUEUES


async def connect() -> RobustConnection:
    return await aio_pika.connect_robust(settings.rabbitmq_url)


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
