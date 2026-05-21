#!/usr/bin/env python3
"""Publish showcase.generate for a stuck project (post-revision idempotency bug recovery)."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "pandora_shared"))

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.component import Component  # noqa: E402
from app.models.thread_message import ThreadMessage  # noqa: E402
from app.services.message_broker import MessageBroker  # noqa: E402
from app.services.pipeline_consumer import (  # noqa: E402
    SHOWCASE_GENERATE_EVENT,
    _build_showcase_work_payload,
)
from pandora_shared.enums import ComponentStatus  # noqa: E402
from pandora_shared.events import MessageEnvelope  # noqa: E402
from pandora_shared.queues import SHOWCASE_GENERATE  # noqa: E402


async def _latest_pipeline_id(session, project_id: int) -> UUID:
    row = await session.scalar(
        select(ThreadMessage.pipeline_id)
        .where(
            ThreadMessage.project_id == project_id,
            ThreadMessage.pipeline_id.is_not(None),
        )
        .order_by(ThreadMessage.id.desc())
        .limit(1)
    )
    if row is None:
        raise SystemExit(f"No pipeline_id on thread messages for project_id={project_id}")
    return row


async def recover(project_id: int, *, dry_run: bool) -> None:
    async with async_session() as session:
        pipeline_id = await _latest_pipeline_id(session, project_id)
        payload = await _build_showcase_work_payload(session, project_id)
        validated = await session.scalar(
            select(Component)
            .where(
                Component.project_id == project_id,
                Component.status == ComponentStatus.validated,
            )
        )
        if validated is None:
            raise SystemExit(f"No validated components for project_id={project_id}")

    print(f"project_id={project_id} pipeline_id={pipeline_id}")
    print(f"validated components in showcase payload: {len(payload.get('components') or [])}")

    if dry_run:
        print("dry-run: would publish pandora.showcase.generate")
        return

    broker = MessageBroker(os.environ.get("RABBITMQ_URL", "amqp://pandora:pandora@localhost:5672/"))
    await broker.connect()
    try:
        envelope = MessageEnvelope(
            event=SHOWCASE_GENERATE_EVENT,
            project_id=project_id,
            pipeline_id=pipeline_id,
            payload=payload,
        )
        await broker.publish(SHOWCASE_GENERATE, envelope)
        print("published pandora.showcase.generate — watch worker-showcase + backend consumer")
    finally:
        await broker.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_id", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(recover(args.project_id, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
