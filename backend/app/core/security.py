"""Self-hosted auth: argon2 password hashing + JWT access/refresh tokens.

Not Firebase (see the plan's MVP-vs-funded stack table) — zero cost, no
vendor account, no cross-border data question. `current_user` is written as
a thin dependency specifically so a departmental OIDC/SSO provider can
replace the JWT-decode step later without touching any route that depends
on it.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status

from app.config import Settings
from app.models.user import UserPublic
from app.repositories.user_repository import UserRepository

ISSUER = "jurisai"
AUDIENCE = "jurisai-api"
ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=7)

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _encode(user_id: str, token_type: str, ttl: timedelta, secret: str, jti: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "type": token_type,
        "jti": jti,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def create_access_token(user_id: str, secret: str) -> str:
    return _encode(user_id, "access", ACCESS_TOKEN_TTL, secret, jti=str(uuid.uuid4()))


def create_refresh_token(user_id: str, secret: str) -> tuple[str, str]:
    """Returns (token, jti) — the jti is stored server-side so logout can revoke it."""
    jti = str(uuid.uuid4())
    return _encode(user_id, "refresh", REFRESH_TOKEN_TTL, secret, jti=jti), jti


def decode_token(token: str, secret: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token, secret, algorithms=["HS256"], issuer=ISSUER, audience=AUDIENCE
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from e

    if payload.get("type") != expected_type:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    return payload


def _get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def _get_user_repository(request: Request) -> UserRepository:
    return request.app.state.user_repository  # type: ignore[no-any-return]


async def current_user(
    request: Request,
    settings: Annotated[Settings, Depends(_get_settings)],
    user_repo: Annotated[UserRepository, Depends(_get_user_repository)],
) -> UserPublic:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")

    token = auth_header.removeprefix("Bearer ").strip()
    payload = decode_token(token, settings.jwt_secret_key, expected_type="access")

    user = user_repo.get_by_id(payload["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


CurrentUser = Annotated[UserPublic, Depends(current_user)]
