"""Integration test fixtures (Postgres required)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.database import async_session, engine


@pytest.fixture(autouse=True)
async def require_postgres() -> None:
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres not available: {exc}")
    yield
    # Release pooled connections so the next async test gets a clean loop/connection.
    await engine.dispose()
