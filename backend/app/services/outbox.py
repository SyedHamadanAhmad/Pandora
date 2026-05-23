"""Transactional outbox enqueue helpers (W-B02)."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox_message import OutboxMessage, OutboxStatus
from pandora_shared.events import MessageEnvelope

OUTBOX_NOTIFY_CHANNEL = "pandora_outbox"


async def enqueue_outbox(
    session: AsyncSession,
    queue_name: str,
    envelope: MessageEnvelope,
    *,
    project_id: int,
    idempotency_key: str,
) -> bool:
    """
    Insert an outbox row in the current transaction.

    Returns ``True`` when a new row was inserted, ``False`` when ``idempotency_key``
    already exists (duplicate enqueue is safe).
    """
    stmt = (
        insert(OutboxMessage)
        .values(
            project_id=project_id,
            queue_name=queue_name,
            payload=envelope.model_dump(mode="json"),
            status=OutboxStatus.pending.value,
            idempotency_key=idempotency_key,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(OutboxMessage.id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
