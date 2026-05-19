"""Stub parse agent — consumes parse work queues, publishes ``pandora.parse.results``."""

from __future__ import annotations

import asyncio
import sys

from aio_pika.abc import AbstractIncomingMessage, AbstractChannel

from pandora_shared.events import MessageEnvelope, PipelineEvent
from pandora_shared.payloads import ParseResultPayload, ParseSource
from pandora_shared.queues import PARSE_IMAGE, PARSE_RESULTS, PARSE_TEXT, PARSE_URL

from pandora_stub import runtime

logger = __import__("logging").getLogger(__name__)

_PARSE_QUEUES: dict[ParseSource, str] = {
    "text": PARSE_TEXT,
    "image": PARSE_IMAGE,
    "url": PARSE_URL,
}


def _parse_data(source: ParseSource, work: MessageEnvelope) -> dict:
    payload = work.payload
    if source == "text":
        return {
            "content": payload.get("content", ""),
            "summary": "stub-text-parse",
        }
    if source == "image":
        return {
            "image_urls": payload.get("image_urls", []),
            "summary": "stub-image-parse",
        }
    return {
        "urls": payload.get("urls", []),
        "summary": "stub-url-parse",
    }


def make_handler(source: ParseSource):
    async def handler(message: AbstractIncomingMessage, channel: AbstractChannel) -> None:
        work = runtime.decode_envelope(message.body)
        data = _parse_data(source, work)
        result = MessageEnvelope(
            event=PipelineEvent.PARSE_RESULTS,
            project_id=work.project_id,
            pipeline_id=work.pipeline_id,
            payload=ParseResultPayload(source=source, data=data).model_dump(),
        )
        await runtime.publish(channel, PARSE_RESULTS, result)
        await message.ack()
        logger.info(
            "stub parse %s project_id=%s pipeline_id=%s",
            source,
            work.project_id,
            work.pipeline_id,
        )

    return handler


async def main(source: ParseSource) -> None:
    runtime.configure_logging("pandora_stub.parse")
    if source not in _PARSE_QUEUES:
        raise SystemExit(f"Invalid parse source: {source!r}")

    queue_name = _PARSE_QUEUES[source]
    connection = await runtime.connect()
    declare_channel = await connection.channel()
    await runtime.declare_topology(declare_channel)
    await declare_channel.close()

    logger.info("stub parse worker listening on %s", queue_name)
    await runtime.run_consumers(connection, [(queue_name, make_handler(source))])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m pandora_stub.parse_worker <text|image|url>")
    asyncio.run(main(sys.argv[1]))  # type: ignore[arg-type]
