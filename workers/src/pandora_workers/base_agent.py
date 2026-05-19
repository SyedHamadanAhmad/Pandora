"""Base class for queue-consuming agents."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from aio_pika.abc import AbstractChannel, AbstractIncomingMessage
from pydantic import BaseModel

from pandora_shared.events import MessageEnvelope

from pandora_workers.runtime import decode_envelope, publish

logger = logging.getLogger(__name__)

Handler = Callable[[AbstractIncomingMessage, AbstractChannel], Awaitable[None]]


class BaseAgent(ABC):
    """Consume work from ``work_queue``, publish result to ``result_queue``."""

    work_queue: str
    result_queue: str

    async def handle_message(
        self,
        message: AbstractIncomingMessage,
        channel: AbstractChannel,
    ) -> None:
        try:
            work = decode_envelope(message.body)
            result = await self.handle_work(work)
            await publish(channel, self.result_queue, result)
            await message.ack()
            logger.info(
                "agent ok work=%s result=%s project_id=%s",
                self.work_queue,
                self.result_queue,
                work.project_id,
            )
        except Exception:
            logger.exception("agent failed queue=%s", self.work_queue)
            await message.nack(requeue=True)

    @abstractmethod
    async def handle_work(self, work: MessageEnvelope) -> MessageEnvelope:
        """Transform a work envelope into a result envelope."""

    def binding(self) -> tuple[str, Handler]:
        return (self.work_queue, self.handle_message)

    @staticmethod
    def validated_payload(model: type[BaseModel], payload: dict) -> dict:
        """Validate agent output before publishing."""
        return model.model_validate(payload).model_dump()
