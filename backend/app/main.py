import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import async_session, engine
from app.pipeline_runtime import (
    consumer_status,
    outbox_dispatcher_status,
    shutdown_pipeline_runtime,
    start_pipeline_runtime,
)
from app.routers import (
    auth_router,
    projects_router,
    storybook_router,
    stream_router,
    thread_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_pipeline_runtime(app)
    try:
        yield
    finally:
        await shutdown_pipeline_runtime(app)
        await engine.dispose()


app = FastAPI(title="Pandora API", version="0.1.0", lifespan=lifespan)

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(storybook_router)
app.include_router(stream_router)
app.include_router(thread_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    checks: dict[str, str] = {"api": "ok"}
    try:
        conn = app.state.rabbitmq_connection
        checks["rabbitmq"] = "ok" if conn and not conn.is_closed else "closed"
    except AttributeError:
        checks["rabbitmq"] = "not_initialized"
    checks["pipeline_consumer"] = consumer_status(app)
    checks["outbox_dispatcher"] = outbox_dispatcher_status(app)
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"
    status = (
        "ok"
        if checks.get("rabbitmq") == "ok"
        and checks.get("postgres") == "ok"
        and checks.get("pipeline_consumer") == "running"
        and checks.get("outbox_dispatcher") == "running"
        else "degraded"
    )
    return {"status": status, "checks": checks}


@app.get("/api/health")
async def api_health():
    return await health()
