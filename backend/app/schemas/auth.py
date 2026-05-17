from pydantic import EmailStr, Field

from app.schemas.common import ApiModel


class RegisterRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(ApiModel):
    user_id: int
