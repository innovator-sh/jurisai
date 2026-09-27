from datetime import datetime

from pydantic import EmailStr, Field

from app.models.base import APIModel


class SignupRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(APIModel):
    email: EmailStr
    password: str


class TokenResponse(APIModel):
    access_token: str
    token_type: str = "bearer"


class UserPublic(APIModel):
    id: str
    email: str
    created_at: datetime
