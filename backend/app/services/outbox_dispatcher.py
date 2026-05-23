"""Outbox dispatcher: LISTEN/NOTIFY wake + periodic poll fallback (W-B02)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import asyncpg
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.outbox_message import OutboxMessage, OutboxStatus
from app.services.message_broker import MessageBroker
from app.services.outbox import OUTBOX_NOTIFY_CHANNEL
from pandora_shared.events import MessageEnvelope

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 2.0
DISPATCH_BATCH_SIZE = 50
MAX_PUBLISH_ATTEMPTS = 10


def asyncpg_dsn(database_url: str) -> str:
    """Convert SQLAlchemy async URL to a plain asyncpg DSN."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return database_url


async def dispatch_pending_batch(broker: MessageBroker) -> int:
    """Publish one batch of pending outbox rows. Returns rows processed."""
    async with async_session() as session:
        result = await session.execute(
            select(OutboxMessage)
            .where(OutboxMessage.status == OutboxStatus.pending)
            .order_by(OutboxMessage.id)
            .limit(DISPATCH_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        rows = list(result.scalars())
        if not rows:
            return 0

        now = datetime.now(timezone.utc)
        for row in rows:
            try:
                envelope = MessageEnvelope.model_validate(row.payload)
                await broker.publish(row.queue_name, envelope)
            except Exception as exc:
                row.attempts += 1
                row.last_error = str(exc)[:2000]
                if row.attempts >= MAX_PUBLISH_ATTEMPTS:
                    row.status = OutboxStatus.failed
                logger.warning(
                    "outbox publish failed id=%s queue=%s attempts=%s error=%s",
                    row.id,
                    row.queue_name,
                    row.attempts,
                    exc,
                )
                continue

            row.status = OutboxStatus.sent
            row.published_at = now
            row.last_error = None
            logger.info(
                "outbox published id=%s queue=%s project_id=%s",
                row.id,
                row.queue_name,
                row.project_id,
            )

        await session.commit()
        return len(rows)


async def run_outbox_dispatcher(
    broker: MessageBroker,
    *,
    shutdown_event: asyncio.Event,
) -> None:
    """
    Drain the outbox using NOTIFY wake-ups with a 2s poll safety net.

    On startup, pending rows from before a crash are published on the first batch.
    """
    wake_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    dsn = asyncpg_dsn(settings.database_url)

    async def _listen_loop() -> None:
        conn: asyncpg.Connection | None = None
        try:
            conn = await asyncpg.connect(dsn)
            await conn.add_listener(
                OUTBOX_NOTIFY_CHANNEL,
                lambda _connection, _pid, _channel, _payload: loop.call_soon_threadsafe(
                    wake_event.set
                ),
            )
            logger.info("outbox dispatcher listening on channel=%s", OUTBOX_NOTIFY_CHANNEL)
            await shutdown_event.wait()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("outbox LISTEN loop failed")
            raise
        finally:
            if conn is not None:
                await conn.close()

    listen_task = asyncio.create_task(_listen_loop(), name="outbox-listen")

    try:
        while not shutdown_event.is_set():
            try:
                while True:
                    processed = await dispatch_pending_batch(broker)
                    if processed < DISPATCH_BATCH_SIZE:
                        break
            except Exception:
                logger.exception("outbox dispatch batch failed")

            wake_event.clear()
            try:
                await asyncio.wait_for(wake_event.wait(), timeout=POLL_INTERVAL_SEC)
            except TimeoutError:
                pass
    except asyncio.CancelledError:
        logger.info("outbox dispatcher cancelled")
        raise
    finally:
        shutdown_event.set()
        listen_task.cancel()
        try:
            await listen_task
        except asyncio.CancelledError:
            pass
