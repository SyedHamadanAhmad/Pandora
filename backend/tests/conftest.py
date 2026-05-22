"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.database import async_session
from app.dependencies import get_message_broker
from app.main import app
from app.models.component import Component
from app.models.design_brief import DesignBrief
from app.models.design_schema import DesignSchema
from app.models.pipeline_run import PipelineRun
from app.models.project import Project
from app.models.thread_message import ThreadMessage
from app.services.message_broker import MessageBroker
from pandora_shared.enums import ComponentStatus, ProjectStatus


@pytest.fixture
def mock_broker() -> MagicMock:
    broker = MagicMock(spec=MessageBroker)
    broker.publish = AsyncMock()
    return broker


@pytest.fixture
async def api_client(mock_broker: MagicMock) -> AsyncClient:
    app.dependency_overrides[get_message_broker] = lambda: mock_broker
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
    app.dependency_overrides.clear()


async def register_and_login(client: AsyncClient) -> int:
    email = f"storybook-{uuid4()}@example.com"
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


async def seed_storybook_library(
    user_id: int,
    *,
    component_status: ComponentStatus = ComponentStatus.validated,
    with_pipeline: bool = True,
) -> tuple[int, int]:
    pipeline_run_id = 9001
    async with async_session() as db:
        project = Project(
            user_id=user_id,
            name="Storybook integration test",
            status=ProjectStatus.completed,
        )
        db.add(project)
        await db.flush()

        brief = DesignBrief(
            project_id=project.id,
            color_tokens={"primary": "#f97316"},
        )
        db.add(brief)
        await db.flush()

        schema = DesignSchema(
            project_id=project.id,
            brief_id=brief.id,
            design_tokens={"primary": "#f97316", "radius": "8px"},
            global_config={"theme": "light"},
            component_specs=[
                {
                    "name": "Button",
                    "type": "button",
                    "variants": ["primary", "secondary"],
                }
            ],
            component_count=1,
        )
        db.add(schema)
        await db.flush()

        component = Component(
            project_id=project.id,
            schema_id=schema.id,
            spec_index=0,
            name="Button",
            status=component_status,
            tsx_code="export function Button() { return <button>OK</button>; }",
            css_code=".btn { color: var(--on-primary); }",
            variants=[{"name": "primary"}],
            props={"label": "Go"},
        )
        db.add(component)
        await db.flush()

        if with_pipeline:
            message = ThreadMessage(
                project_id=project.id,
                user_id=user_id,
                role="user",
                content="hi",
            )
            db.add(message)
            await db.flush()
            run = PipelineRun(
                project_id=project.id,
                thread_message_id=message.id,
                parse_expected=1,
                parse_received=1,
                parse_pending=[],
                run_complete=True,
            )
            db.add(run)
            await db.flush()
            message.pipeline_run_id = run.id
        await db.commit()
        await db.refresh(component)
        return project.id, component.id
