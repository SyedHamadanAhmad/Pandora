"""SSE Redis relay lifecycle (W-B04)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI

from app.services.sse_relay import run_sse_relay

logger = logging.getLogger(__name__)


def sse_relay_status(app: FastAPI) -> str:
    task = getattr(app.state, "sse_relay_task", None)
    if task is None:
        return "not_started"
    if not task.done():
        return "running"
    if task.cancelled():
        return "stopped"
    if task.exception() is not None:
        return "failed"
    return "stopped"


async def start_sse_runtime(app: FastAPI) -> None:
    app.state.sse_shutdown = asyncio.Event()
    app.state.sse_relay_task = asyncio.create_task(
        run_sse_relay(shutdown_event=app.state.sse_shutdown),
        name="sse-relay",
    )
    logger.info("sse relay task started")


async def shutdown_sse_runtime(app: FastAPI) -> None:
    shutdown_event = getattr(app.state, "sse_shutdown", None)
    if shutdown_event is not None:
        shutdown_event.set()

    task = getattr(app.state, "sse_relay_task", None)
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    logger.info("sse runtime shut down")
