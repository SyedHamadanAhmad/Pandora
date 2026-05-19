"""In-process SSE fan-out for pipeline progress (Phase 3 Step 6)."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, AsyncIterator

HEARTBEAT_INTERVAL_SECONDS = 20
_SUBSCRIBER_QUEUE_MAXSIZE = 50

_lock = asyncio.Lock()
_subscribers: dict[int, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)


def emit(project_id: int, event: dict[str, Any]) -> None:
    """Push a project-scoped event to connected SSE clients; drop if a client is slow."""
    queues = _subscribers.get(project_id)
    if not queues:
        return
    for queue in list(queues):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass


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
