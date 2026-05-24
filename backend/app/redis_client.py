"""Async Redis connection for SSE pub/sub (W-B04)."""

from __future__ import annotations

import logging

from redis.asyncio import Redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


async def connect_redis() -> Redis:
    """Open the shared Redis client (call once at app startup)."""
    global _redis
    if _redis is not None:
        return _redis
    _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await _redis.ping()
    logger.info("redis connected url=%s", settings.redis_url.split("@")[-1])
    return _redis


def get_redis() -> Redis | None:
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("redis connection closed")


async def ping_redis() -> bool:
    client = get_redis()
    if client is None:
        return False
    try:
        await client.ping()
        return True
    except Exception:
        logger.exception("redis ping failed")
        return False
