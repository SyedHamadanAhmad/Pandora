from app.routers.auth import router as auth_router
from app.routers.projects import router as projects_router
from app.routers.thread import router as thread_router

__all__ = ["auth_router", "projects_router", "thread_router"]
