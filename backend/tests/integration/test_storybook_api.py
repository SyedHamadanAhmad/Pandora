"""
Storybook API integration tests (Phase 5).

Run inside Compose:

  docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend \\
    pytest tests/integration/test_storybook_api.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from pandora_shared.enums import ComponentStatus
from pandora_shared.sse_events import COMPONENT_REVISION_STARTED
from tests.conftest import register_and_login, seed_storybook_library


@pytest.mark.asyncio
async def test_storybook_overview_and_component_detail(api_client: AsyncClient) -> None:
    user_id = await register_and_login(api_client)
    project_id, component_id = await seed_storybook_library(user_id)

    overview = await api_client.get(f"/api/projects/{project_id}/storybook")
    assert overview.status_code == 200
    body = overview.json()
    assert body["projectId"] == project_id
    assert body["projectStatus"] == "completed"
    assert body["designTokens"]["primary"] == "#f97316"
    assert body["designTokens"]["onPrimary"] == "#ffffff"
    assert "primary" in body["tokenSchema"]["editable"]
    assert len(body["tokenSchema"]["semanticPairs"]) == 4
    assert body["summary"]["validated"] == 1
    assert body["components"][0]["previewAvailable"] is True
    assert "export function Button" in body["components"][0]["tsxPreview"]

    detail = await api_client.get(f"/api/projects/{project_id}/components/{component_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["component"]["name"] == "Button"
    assert detail_body["spec"]["type"] == "button"
    assert detail_body["designTokens"]["onPrimary"] == "#ffffff"

    missing = await api_client.get(f"/api/projects/{project_id}/components/999999")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_storybook_forbidden_for_other_user(api_client: AsyncClient) -> None:
    owner_id = await register_and_login(api_client)
    project_id, _ = await seed_storybook_library(owner_id)

    other_email = f"other-{uuid4()}@example.com"
    await api_client.post(
        "/api/auth/register",
        json={"email": other_email, "password": "secret123"},
    )
    login = await api_client.post(
        "/api/auth/login",
        json={"email": other_email, "password": "secret123"},
    )
    api_client.cookies.update(login.cookies)

    forbidden = await api_client.get(f"/api/projects/{project_id}/storybook")
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_storybook_unauthenticated() -> None:
    from httpx import ASGITransport

    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/projects/1/storybook")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_patch_and_apply_tokens(api_client: AsyncClient) -> None:
    user_id = await register_and_login(api_client)
    project_id, _ = await seed_storybook_library(user_id)

    patch = await api_client.patch(
        f"/api/projects/{project_id}/storybook/tokens",
        json={"designTokens": {"primary": "#ea580c"}},
    )
    assert patch.status_code == 200
    assert patch.json()["designTokens"]["primary"] == "#ea580c"

    apply = await api_client.post(
        f"/api/projects/{project_id}/storybook/tokens/apply",
        json={"designTokens": {"radius": "16px"}, "regenerateComponents": False},
    )
    assert apply.status_code == 202
    body = apply.json()
    assert body["regenerateQueued"] == 0
    assert body["status"] == "applied"
    assert body["designTokens"]["radius"] == "16px"


@pytest.mark.asyncio
async def test_apply_tokens_with_regen(api_client: AsyncClient) -> None:
    user_id = await register_and_login(api_client)
    project_id, _ = await seed_storybook_library(user_id)

    with patch(
        "app.services.storybook_tokens.fanout_token_regeneration",
        new_callable=AsyncMock,
        return_value=1,
    ) as fanout:
        response = await api_client.post(
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


@pytest.mark.asyncio
async def test_suggest_tokens_mocked_llm(api_client: AsyncClient) -> None:
    user_id = await register_and_login(api_client)
    project_id, _ = await seed_storybook_library(user_id)

    with patch(
        "app.services.openrouter_client.complete_json",
        new_callable=AsyncMock,
        return_value={
            "design_tokens": {"text_muted": "#94a3b8"},
            "explanation": "Softened muted text.",
        },
    ):
        response = await api_client.post(
            f"/api/projects/{project_id}/storybook/tokens/suggest",
            json={"message": "Softer muted gray"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["proposedTokens"]["textMuted"] == "#94a3b8"
    assert "Softened" in body["explanation"]

    overview = await api_client.get(f"/api/projects/{project_id}/storybook")
    assert overview.json()["designTokens"]["primary"] == "#f97316"


@pytest.mark.asyncio
async def test_tokens_conflict_when_library_busy(api_client: AsyncClient) -> None:
    user_id = await register_and_login(api_client)
    project_id, _ = await seed_storybook_library(
        user_id,
        component_status=ComponentStatus.generating,
    )

    patch = await api_client.patch(
        f"/api/projects/{project_id}/storybook/tokens",
        json={"designTokens": {"primary": "#000000"}},
    )
    assert patch.status_code == 409


@pytest.mark.asyncio
async def test_component_revise(api_client: AsyncClient, mock_broker) -> None:
    user_id = await register_and_login(api_client)
    project_id, component_id = await seed_storybook_library(user_id)

    with patch("app.services.storybook_revise.sse_service.emit") as emit_sse:
        response = await api_client.post(
            f"/api/projects/{project_id}/components/{component_id}/revise",
            json={"message": "Use white text on the primary button"},
        )
    assert response.status_code == 202
    body = response.json()
    assert body["componentId"] == component_id
    assert body["status"] == "generating"

    emit_sse.assert_called_once()
    event = emit_sse.call_args[0][1]
    assert event["type"] == COMPONENT_REVISION_STARTED
    assert event["projectId"] == project_id
    assert event["componentId"] == str(component_id)

    mock_broker.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_component_revise_conflict_when_generating(api_client: AsyncClient) -> None:
    user_id = await register_and_login(api_client)
    project_id, component_id = await seed_storybook_library(
        user_id,
        component_status=ComponentStatus.generating,
    )

    response = await api_client.post(
        f"/api/projects/{project_id}/components/{component_id}/revise",
        json={"message": "fix it"},
    )
    assert response.status_code == 409


