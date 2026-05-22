"""
Phase 2 integration test: auth → project → multipart thread → MinIO.

Run inside Compose so Postgres and MinIO are reachable:

  docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm backend \\
    pytest tests/integration/test_auth_projects.py -v
"""

from __future__ import annotations

import io
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from minio import Minio
from sqlalchemy import select, text

from app.config import settings
from app.database import async_session
from app.main import app
from app.models.thread_message import ThreadMessage
from app.services.auth_service import SESSION_COOKIE

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
)


@pytest.fixture
async def api_client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture(autouse=True)
async def require_postgres() -> None:
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres not available: {exc}")


@pytest.mark.asyncio
async def test_register_login_project_thread_and_minio(api_client: AsyncClient) -> None:
    email = f"integration-{uuid4()}@example.com"
    password = "secret123"

    register = await api_client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert register.status_code == 201
    assert "userId" in register.json()

    login = await api_client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    assert SESSION_COOKIE in login.cookies

    project = await api_client.post(
        "/api/projects/",
        json={"name": "Integration test project"},
        cookies=login.cookies,
    )
    assert project.status_code == 201
    project_id = project.json()["id"]
    assert project.json()["status"] == "pending"

    thread = await api_client.post(
        f"/api/projects/{project_id}/thread/",
        data={
            "content": "Modern SaaS dashboard",
            "urls": '["https://example.com"]',
        },
        files=[("images", ("shot.png", io.BytesIO(PNG_BYTES), "image/png"))],
        cookies=login.cookies,
    )
    assert thread.status_code == 201
    message_id = thread.json()["messageId"]
    assert "pipelineId" not in thread.json()

    history = await api_client.get(
        f"/api/projects/{project_id}/thread/",
        cookies=login.cookies,
    )
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert len(messages) == 1
    assert messages[0]["pipelineId"] is not None
    assert len(messages[0]["inputImageUrls"]) == 1

    components = await api_client.get(
        f"/api/projects/{project_id}/components",
        cookies=login.cookies,
    )
    assert components.status_code == 200
    assert components.json() == {"components": []}

    async with async_session() as db:
        row = await db.execute(
            select(ThreadMessage).where(ThreadMessage.id == message_id)
        )
        message = row.scalar_one()
        assert message.pipeline_id is not None
        assert message.input_image_urls
        object_key = _object_key_from_url(message.input_image_urls[0])

    _assert_minio_object_exists(object_key)

    logout = await api_client.post("/api/auth/logout", cookies=login.cookies)
    assert logout.status_code == 204


def _object_key_from_url(url: str) -> str:
    """Extract ``{project_id}/messages/{message_id}/{file}`` from stored URL."""
    prefix = f"{settings.minio_bucket}/"
    idx = url.find(prefix)
    assert idx != -1, f"Unexpected image URL format: {url}"
    return url[idx + len(prefix) :]


def _assert_minio_object_exists(object_key: str) -> None:
    parsed = urlparse(settings.minio_endpoint)
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    client = Minio(
        host,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=parsed.scheme == "https",
    )
    stat = client.stat_object(settings.minio_bucket, object_key)
    assert stat.size > 0
