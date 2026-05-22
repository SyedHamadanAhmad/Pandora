"""Unit tests for storybook token merge, validation, and routes."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import async_session
from app.dependencies import get_message_broker
from app.main import app
from app.services.message_broker import MessageBroker
from app.models.component import Component
from app.models.design_brief import DesignBrief
from app.models.design_schema import DesignSchema
from app.models.project import Project
from app.models.thread_message import ThreadMessage
from app.services.storybook_tokens import (
    merge_design_tokens,
    validate_and_filter_patch,
)
from pandora_shared.enums import ComponentStatus, ProjectStatus


class StorybookTokenLogicTests(unittest.TestCase):
    def test_merge_enriches_on_primary(self) -> None:
        merged = merge_design_tokens({"primary": "#f97316"}, {"radius": "12px"})
        self.assertEqual(merged["radius"], "12px")
        self.assertEqual(merged["on_primary"], "#ffffff")

    def test_rejects_unknown_key(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            validate_and_filter_patch({"not_a_token": "#fff"})
        self.assertEqual(ctx.exception.status_code, 400)

    def test_accepts_camel_case_keys(self) -> None:
        patch = validate_and_filter_patch({"textMuted": "#94a3b8"})
        self.assertEqual(patch["text_muted"], "#94a3b8")


def _mock_broker() -> MagicMock:
    broker = MagicMock(spec=MessageBroker)
    broker.publish = AsyncMock()
    return broker


async def _register_and_login(client: AsyncClient) -> int:
    email = f"tokens-{uuid4()}@example.com"
    password = "secret123"
    register = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert register.status_code == 201
    user_id = register.json()["userId"]
    login = await client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    client.cookies.update(login.cookies)
    return user_id


async def _seed_library(user_id: int) -> tuple[int, int]:
    pipeline_id = uuid4()
    async with async_session() as db:
        project = Project(
            user_id=user_id,
            name="Token test",
            status=ProjectStatus.completed,
        )
        db.add(project)
        await db.flush()

        brief = DesignBrief(project_id=project.id)
        db.add(brief)
        await db.flush()

        schema = DesignSchema(
            project_id=project.id,
            brief_id=brief.id,
            design_tokens={"primary": "#f97316", "radius": "8px"},
            global_config={"theme": "light"},
            component_specs=[{"name": "Button", "type": "button"}],
            component_count=1,
        )
        db.add(schema)
        await db.flush()

        component = Component(
            project_id=project.id,
            schema_id=schema.id,
            spec_index=0,
            name="Button",
            status=ComponentStatus.validated,
            tsx_code="export const Button = () => null;",
        )
        db.add(component)
        await db.flush()

        db.add(
            ThreadMessage(
                project_id=project.id,
                user_id=user_id,
                role="user",
                content="hi",
                pipeline_id=pipeline_id,
            )
        )
        await db.commit()
        return project.id, component.id


async def test_patch_and_apply_without_regen() -> None:
    app.dependency_overrides[get_message_broker] = lambda: _mock_broker()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            user_id = await _register_and_login(client)
            project_id, _ = await _seed_library(user_id)

            patch = await client.patch(
                f"/api/projects/{project_id}/storybook/tokens",
                json={"designTokens": {"primary": "#ea580c"}},
            )
            assert patch.status_code == 200
            assert patch.json()["designTokens"]["primary"] == "#ea580c"
            assert patch.json()["designTokens"]["onPrimary"] == "#ffffff"

            apply = await client.post(
                f"/api/projects/{project_id}/storybook/tokens/apply",
                json={
                    "designTokens": {"radius": "16px"},
                    "regenerateComponents": False,
                },
            )
            assert apply.status_code == 202
            body = apply.json()
            assert body["regenerateQueued"] == 0
            assert body["status"] == "applied"
            assert body["designTokens"]["radius"] == "16px"
    finally:
        app.dependency_overrides.clear()


async def test_apply_with_regen_publishes() -> None:
    app.dependency_overrides[get_message_broker] = lambda: _mock_broker()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            user_id = await _register_and_login(client)
            project_id, _ = await _seed_library(user_id)

            with patch(
                "app.services.storybook_tokens.fanout_token_regeneration",
                new_callable=AsyncMock,
                return_value=1,
            ) as fanout:
                response = await client.post(
                    f"/api/projects/{project_id}/storybook/tokens/apply",
                    json={
                        "designTokens": {"primary": "#c2410c"},
                        "regenerateComponents": True,
                    },
                )
            assert response.status_code == 202
            assert response.json()["regenerateQueued"] == 1
            assert response.json()["status"] == "token_apply_running"
            fanout.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()


async def test_suggest_mocked_llm() -> None:
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            user_id = await _register_and_login(client)
            project_id, _ = await _seed_library(user_id)

            with patch(
                "app.services.storybook_tokens.complete_json",
                new_callable=AsyncMock,
                return_value={
                    "design_tokens": {"text_muted": "#94a3b8"},
                    "explanation": "Softened muted text.",
                },
            ):
                response = await client.post(
                    f"/api/projects/{project_id}/storybook/tokens/suggest",
                    json={"message": "Softer muted gray"},
                )
            assert response.status_code == 200
            body = response.json()
            assert body["proposedTokens"]["textMuted"] == "#94a3b8"
            assert body["designTokens"]["textMuted"] == "#94a3b8"
            assert "Softened" in body["explanation"]

            overview = await client.get(f"/api/projects/{project_id}/storybook")
            assert overview.json()["designTokens"]["primary"] == "#f97316"
    finally:
        app.dependency_overrides.clear()


async def test_conflict_when_component_generating() -> None:
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            user_id = await _register_and_login(client)
            project_id, _ = await _seed_library(user_id)
            async with async_session() as db:
                component = await db.scalar(
                    select(Component).where(Component.project_id == project_id)
                )
                assert component is not None
                component.status = ComponentStatus.generating
                await db.commit()

            patch = await client.patch(
                f"/api/projects/{project_id}/storybook/tokens",
                json={"designTokens": {"primary": "#000000"}},
            )
            assert patch.status_code == 409
    finally:
        app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
