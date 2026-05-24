"""Redis Pub/Sub relay → local SSE subscribers (W-B04)."""

from __future__ import annotations

import asyncio
import json
import logging

from app.redis_client import get_redis
from app.services.sse_service import SSE_CHANNEL_PATTERN, deliver_local, project_id_from_channel

logger = logging.getLogger(__name__)

_RELAY_POLL_TIMEOUT_SEC = 1.0


async def run_sse_relay(*, shutdown_event: asyncio.Event) -> None:
    """
    Subscribe to ``sse:project:*`` and forward each message to in-process SSE queues.

    ``emit()`` only PUBLISHes to Redis; this task is the sole path to ``deliver_local``.
    """
    redis = get_redis()
    if redis is None:
        logger.error("sse relay cannot start: redis not connected")
        return

    pubsub = redis.pubsub()
    await pubsub.psubscribe(SSE_CHANNEL_PATTERN)
    logger.info("sse relay subscribed pattern=%s", SSE_CHANNEL_PATTERN)

    try:
        while not shutdown_event.is_set():
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=_RELAY_POLL_TIMEOUT_SEC,
            )
            if message is None:
                continue
            if message.get("type") != "pmessage":
                continue

            channel = message.get("channel")
            if not isinstance(channel, str):
                continue

            try:
                project_id = project_id_from_channel(channel)
            except ValueError:
                logger.warning("sse relay ignored unknown channel=%s", channel)
                continue

            raw = message.get("data")
            if not isinstance(raw, str):
                continue

            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("sse relay invalid json on channel=%s", channel)
                continue

            if not isinstance(event, dict):
                continue

            deliver_local(project_id, event)
    except asyncio.CancelledError:
        logger.info("sse relay cancelled")
        raise
    except Exception:
        logger.exception("sse relay exited with error")
        raise
    finally:
        try:
            await pubsub.punsubscribe(SSE_CHANNEL_PATTERN)
            await pubsub.aclose()
        except Exception:
            logger.exception("sse relay pubsub cleanup failed")
