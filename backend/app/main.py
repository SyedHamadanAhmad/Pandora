import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import rabbitmq
from app.database import async_session, engine
from app.routers import auth_router, projects_router, thread_router
from app.services import pipeline_consumer
from app.services.message_broker import MessageBroker
from app.services.pipeline_state import recover_running_projects


@asynccontextmanager
async def lifespan(app: FastAPI):
    connection = await rabbitmq.connect()
    channel = await connection.channel()
    await rabbitmq.declare_topology(channel)
    app.state.rabbitmq_connection = connection
    app.state.rabbitmq_channel = channel
    broker = MessageBroker(channel)
    app.state.message_broker = broker

    await recover_running_projects()
    pipeline_consumer.wire_parses_complete_callbacks(broker)

    consumer_task = asyncio.create_task(
        pipeline_consumer.run_forever(connection, broker),
        name="pipeline-consumer",
    )
    app.state.pipeline_consumer_task = consumer_task

    yield

    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await connection.close()
    await engine.dispose()


app = FastAPI(title="Pandora API", version="0.1.0", lifespan=lifespan)

app.include_router(auth_router)
app.include_router(projects_router)
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
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"
    status = (
        "ok"
        if checks.get("rabbitmq") == "ok" and checks.get("postgres") == "ok"
        else "degraded"
    )
    return {"status": status, "checks": checks}


@app.get("/api/health")
async def api_health():
    return await health()
