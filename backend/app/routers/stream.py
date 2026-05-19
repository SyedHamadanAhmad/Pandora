"""SSE stream for live pipeline progress (Phase 3 Step 6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.session_auth import get_current_user_id
from app.routers.projects import _get_project_for_user
from app.services import sse_service

router = APIRouter(prefix="/api/projects", tags=["stream"])


@router.get("/{project_id}/stream")
async def project_stream(
    project_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    await _get_project_for_user(db, project_id, user_id)
    return StreamingResponse(
        sse_service.stream_chunks(project_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
