"""SSE fan-out: Redis Streams (replay) + Pub/Sub (live) across replicas (W-B04)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, AsyncIterator

from app.config import settings
from app.redis_client import get_redis

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 20
_SUBSCRIBER_QUEUE_MAXSIZE = 50

# Hash tag {project_id} keeps stream + pub channel in one slot (Cluster + MULTI/EXEC).
_SSE_HASH_PREFIX = "sse:{"
_SSE_PUB_SUFFIX = "}:pub"
SSE_CHANNEL_PATTERN = "sse:*:pub"

_lock = asyncio.Lock()
_subscribers: dict[int, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)


def stream_key_for_project(project_id: int) -> str:
    return f"sse:{{{project_id}}}:stream"


def channel_for_project(project_id: int) -> str:
    return f"sse:{{{project_id}}}:pub"


def project_id_from_channel(channel: str) -> int:
    prefix = "sse:"
    suffix = ":pub"
    if not channel.startswith(prefix) or not channel.endswith(suffix):
        raise ValueError(f"not a project sse channel: {channel!r}")
    inner = channel[len(prefix) : -len(suffix)]
    if inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1]
    return int(inner)


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


async def replay_stream(
    project_id: int,
    *,
    after_id: str | None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Yield events from the per-project Redis stream.

    When ``after_id`` is set (SSE reconnect), replay entries after that id.
    On first connect (no ``Last-Event-ID``), replay the full buffered stream so
    clients do not miss events emitted before subscribe.
    """
    redis = get_redis()
    if redis is None:
        return

    stream = stream_key_for_project(project_id)
    try:
        if after_id:
            entries = await redis.xrange(stream, min=f"({after_id}", max="+")
        else:
            entries = await redis.xrange(stream, min="-", max="+")
    except Exception:
        logger.exception("sse stream replay failed project_id=%s", project_id)
        return

    for entry_id, fields in entries:
        raw = fields.get("payload") if isinstance(fields, dict) else None
        if not isinstance(raw, str):
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("sse stream invalid payload project_id=%s id=%s", project_id, entry_id)
            continue
        if not isinstance(event, dict):
            continue
        yield {**event, "sseId": entry_id}


async def publish_to_redis(project_id: int, event: dict[str, Any]) -> None:
    """
    Atomically append to the project stream and notify all API replicas (MULTI/EXEC).

    Both commands carry the same JSON payload so stream replay and live Pub/Sub stay aligned.
    Reconnect replay attaches ``sseId`` from the stream entry id; live Pub/Sub uses the same body.
    """
    redis = get_redis()
    if redis is None:
        deliver_local(project_id, event)
        return

    payload = json.dumps(event, separators=(",", ":"))
    stream = stream_key_for_project(project_id)
    channel = channel_for_project(project_id)
    maxlen = settings.sse_stream_maxlen

    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.xadd(
                stream,
                {"payload": payload},
                maxlen=maxlen,
                approximate=True,
            )
            pipe.publish(channel, payload)
            await pipe.execute()
    except Exception:
        logger.exception(
            "sse atomic publish failed project_id=%s; delivering locally only",
            project_id,
        )
        deliver_local(project_id, event)


def emit(project_id: int, event: dict[str, Any]) -> None:
    """
    Publish a project-scoped event for all SSE subscribers (all API replicas).

    Uses Redis Stream + Pub/Sub in one MULTI/EXEC batch; each replica's ``sse_relay``
    forwards live messages via ``deliver_local``.
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
    sse_id = event.get("sseId")
    data = json.dumps(event, separators=(",", ":"))
    if isinstance(sse_id, str) and sse_id:
        return f"id: {sse_id}\nevent: message\ndata: {data}\n\n"
    return f"event: message\ndata: {data}\n\n"


def format_sse_ping() -> str:
    return ": ping\n\n"


async def stream_chunks(
    project_id: int,
    *,
    last_event_id: str | None = None,
) -> AsyncIterator[str]:
    """Replay buffered stream events, then live SSE with heartbeat pings when idle."""
    async for event in replay_stream(project_id, after_id=last_event_id):
        yield format_sse_message(event)

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
