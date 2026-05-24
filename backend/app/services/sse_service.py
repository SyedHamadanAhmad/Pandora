"""SSE fan-out: Redis Pub/Sub across replicas + local connection queues (W-B04)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, AsyncIterator

from app.redis_client import get_redis

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 20
_SUBSCRIBER_QUEUE_MAXSIZE = 50

SSE_CHANNEL_PREFIX = "sse:project:"
SSE_CHANNEL_PATTERN = f"{SSE_CHANNEL_PREFIX}*"

_lock = asyncio.Lock()
_subscribers: dict[int, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)


def channel_for_project(project_id: int) -> str:
    return f"{SSE_CHANNEL_PREFIX}{project_id}"


def project_id_from_channel(channel: str) -> int:
    prefix = SSE_CHANNEL_PREFIX
    if not channel.startswith(prefix):
        raise ValueError(f"not a project sse channel: {channel!r}")
    return int(channel[len(prefix) :])


def deliver_local(project_id: int, event: dict[str, Any]) -> None:
    """Push an event to SSE clients connected to this API process only."""
    queues = _subscribers.get(project_id)
    if not queues:
        return
    for queue in list(queues):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass


async def publish_to_redis(project_id: int, event: dict[str, Any]) -> None:
    """Publish a project event to Redis for all API replicas."""
    redis = get_redis()
    if redis is None:
        deliver_local(project_id, event)
        return

    payload = json.dumps(event, separators=(",", ":"))
    await redis.publish(channel_for_project(project_id), payload)


def emit(project_id: int, event: dict[str, Any]) -> None:
    """
    Publish a project-scoped event for all SSE subscribers (all API replicas).

    Uses Redis PUBLISH; each replica's ``sse_relay`` calls ``deliver_local``.
    If Redis is unavailable or no event loop is running, delivers locally only.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        deliver_local(project_id, event)
        return

    loop.create_task(publish_to_redis(project_id, event))


async def subscribe(project_id: int) -> AsyncIterator[dict[str, Any]]:
    """Yield events for one SSE connection until the client disconnects."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_MAXSIZE)
    async with _lock:
        _subscribers[project_id].add(queue)
    try:
        while True:
            yield await queue.get()
    finally:
        async with _lock:
            _subscribers[project_id].discard(queue)
            if not _subscribers[project_id]:
                del _subscribers[project_id]


def format_sse_message(event: dict[str, Any]) -> str:
    data = json.dumps(event, separators=(",", ":"))
    return f"event: message\ndata: {data}\n\n"


def format_sse_ping() -> str:
    return ": ping\n\n"


async def stream_chunks(project_id: int) -> AsyncIterator[str]:
    """SSE wire format with heartbeat comments when idle."""
    subscription = subscribe(project_id)
    while True:
        try:
            event = await asyncio.wait_for(
                subscription.__anext__(),
                timeout=HEARTBEAT_INTERVAL_SECONDS,
            )
        except asyncio.TimeoutError:
            yield format_sse_ping()
            continue
        except StopAsyncIteration:
            break
        yield format_sse_message(event)
