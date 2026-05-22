"""Unit tests for idempotency service."""

import unittest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.services.idempotency import (
    IdempotencyStatus,
    idempotency_key_for_envelope,
    parse_results_idempotency_key,
    run_idempotent,
)
from pandora_shared.events import (
    Attempt,
    MessageEnvelope,
    PipelineEvent,
    build_idempotency_key,
)
from pandora_shared.payloads import ParseResultPayload


class IdempotencyKeyTests(unittest.TestCase):
    def test_key_for_envelope_with_component_attempt(self) -> None:
        pipeline_id = 42
        component_id = 42
        envelope = MessageEnvelope(
            event="pandora.component.validated",
            project_id=1,
            pipeline_id=pipeline_id,
            component_id=component_id,
            attempt=Attempt(retry_count=0, revision_round=1),
        )
        key = idempotency_key_for_envelope(envelope)
        self.assertEqual(
            key,
            build_idempotency_key(
                pipeline_id,
                "pandora.component.validated",
                component_id=component_id,
                attempt=Attempt(retry_count=0, revision_round=1),
            ),
        )

    def test_verification_start_key_includes_revision_round(self) -> None:
        pipeline_id = 42
        key = build_idempotency_key(
            pipeline_id,
            "pandora.verification.start",
            attempt=Attempt(revision_round=2),
        )
        self.assertEqual(key, f"{pipeline_id}:pandora.verification.start:0.2")

    def test_parse_results_key_includes_source(self) -> None:
        pipeline_id = 42
        key = parse_results_idempotency_key(pipeline_id, "text")
        self.assertEqual(key, f"{pipeline_id}:pandora.parse.results:text")

    def test_idempotency_key_for_parse_result_envelope(self) -> None:
        pipeline_id = 42
        envelope = MessageEnvelope(
            event=PipelineEvent.PARSE_RESULTS,
            project_id=1,
            pipeline_id=pipeline_id,
            payload=ParseResultPayload(source="text", data={"x": 1}).model_dump(),
        )
        key = idempotency_key_for_envelope(envelope)
        self.assertEqual(key, f"{pipeline_id}:pandora.parse.results:text")


class RunIdempotentTests(unittest.IsolatedAsyncioTestCase):
    def _mock_session(self) -> MagicMock:
        session = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    async def test_applied_runs_handler_and_commits(self) -> None:
        session = self._mock_session()
        handler = AsyncMock(return_value="ok")

        status, result = await run_idempotent(
            session,
            idempotency_key="pipe:event",
            project_id=1,
            handler=handler,
        )

        self.assertEqual(status, IdempotencyStatus.APPLIED)
        self.assertEqual(result, "ok")
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        handler.assert_awaited_once_with(session)
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    async def test_duplicate_skips_handler(self) -> None:
        session = self._mock_session()
        session.flush = AsyncMock(side_effect=IntegrityError("insert", {}, Exception()))
        handler = AsyncMock()

        status, result = await run_idempotent(
            session,
            idempotency_key="pipe:event",
            project_id=1,
            handler=handler,
        )

        self.assertEqual(status, IdempotencyStatus.DUPLICATE)
        self.assertIsNone(result)
        handler.assert_not_awaited()
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    async def test_handler_error_rolls_back(self) -> None:
        session = self._mock_session()
        handler = AsyncMock(side_effect=RuntimeError("db write failed"))

        with self.assertRaises(RuntimeError):
            await run_idempotent(
                session,
                idempotency_key="pipe:event",
                project_id=1,
                handler=handler,
            )

        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()


class RunIdempotentIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Requires Postgres (run inside backend container)."""

    async def asyncSetUp(self) -> None:
        from sqlalchemy import text

        from app.database import async_session

        try:
            async with async_session() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:
            self.skipTest(f"Postgres not available: {exc}")

    async def test_duplicate_delivery_only_applies_once(self) -> None:
        from sqlalchemy import select

        from app.database import async_session
        from app.models.processed_event import ProcessedEvent
        from app.models.project import Project
        from app.models.user import User
        from pandora_shared.enums import ProjectStatus

        pipeline_id = 42
        key = f"{pipeline_id}:pandora.brief.ready"
        calls = 0

        async def handler(_session) -> int:
            nonlocal calls
            calls += 1
            return calls

        async with async_session() as session:
            user = User(email=f"idempotency-{uuid4()}@test.local", password_hash="hash")
            session.add(user)
            await session.flush()
            project = Project(
                user_id=user.id,
                name="idempotency test",
                status=ProjectStatus.pending,
            )
            session.add(project)
            await session.commit()
            user_id = user.id
            project_id = project.id

        async with async_session() as session:
            status1, value1 = await run_idempotent(
                session,
                idempotency_key=key,
                project_id=project_id,
                handler=handler,
            )
        async with async_session() as session:
            status2, value2 = await run_idempotent(
                session,
                idempotency_key=key,
                project_id=project_id,
                handler=handler,
            )

        self.assertEqual(status1, IdempotencyStatus.APPLIED)
        self.assertEqual(value1, 1)
        self.assertEqual(status2, IdempotencyStatus.DUPLICATE)
        self.assertIsNone(value2)
        self.assertEqual(calls, 1)

        async with async_session() as session:
            rows = (
                await session.execute(
                    select(ProcessedEvent).where(ProcessedEvent.idempotency_key == key)
                )
            ).scalars().all()
            self.assertEqual(len(rows), 1)

        async with async_session() as session:
            u = await session.get(User, user_id)
            if u is not None:
                await session.delete(u)
                await session.commit()


if __name__ == "__main__":
    unittest.main()
