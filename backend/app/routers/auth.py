"""Authentication routes (Tech Spec §4, §8)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.session_auth import SESSION_COOKIE, get_current_user_id
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest
from app.services import auth_service
from app.services.auth_service import DuplicateEmailError

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    try:
        user = await auth_service.create_user(db, body.email, body.password)
        await db.commit()
    except DuplicateEmailError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from None
    return AuthResponse(user_id=user.id)


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    user = await auth_service.get_user_by_email(db, body.email)
    if user is None or not auth_service.verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    session = await auth_service.create_session(db, user.id)
    await db.commit()

    payload = AuthResponse(user_id=user.id).model_dump(mode="json", by_alias=True)
    response = JSONResponse(content=payload)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=str(session.id),
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    pandora_session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    _user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if pandora_session:
        try:
            session_id = UUID(pandora_session)
            await auth_service.delete_session(db, session_id)
            await db.commit()
        except ValueError:
            pass

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return response
