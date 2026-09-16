"""Real signup/login, replacing the legacy `login.html` fake submit (D019)
that only ran `setTimeout` + `console.log`.

Access token: returned in the response body, held in memory by the client,
**never in localStorage** (XSS on a JS-readable store would hand over the
whole session). Refresh token: httpOnly cookie, tracked server-side by jti
so logout can actually revoke it rather than just deleting the cookie.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.security import (
    REFRESH_TOKEN_TTL,
    create_access_token,
    create_refresh_token,
    current_user,
    decode_token,
    hash_password,
    verify_password,
)
from app.deps import RefreshTokenRepositoryDep, SettingsDep, UserRepositoryDep
from app.models.user import LoginRequest, SignupRequest, TokenResponse, UserPublic
from app.repositories.user_repository import EmailAlreadyRegistered

router = APIRouter()

REFRESH_COOKIE = "refresh_token"


def _issue_tokens(
    response: Response,
    user_id: str,
    settings: SettingsDep,
    refresh_repo: RefreshTokenRepositoryDep,
) -> TokenResponse:
    access_token = create_access_token(user_id, settings.jwt_secret_key)
    refresh_token, jti = create_refresh_token(user_id, settings.jwt_secret_key)
    refresh_repo.store(jti, user_id, datetime.now(UTC) + REFRESH_TOKEN_TTL)
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        httponly=True,
        samesite="strict",
        max_age=int(REFRESH_TOKEN_TTL.total_seconds()),
    )
    return TokenResponse(access_token=access_token)


@router.post("/auth/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(
    body: SignupRequest,
    response: Response,
    user_repo: UserRepositoryDep,
    refresh_repo: RefreshTokenRepositoryDep,
    settings: SettingsDep,
) -> TokenResponse:
    try:
        user = user_repo.create(body.email, hash_password(body.password))
    except EmailAlreadyRegistered as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from e
    return _issue_tokens(response, user.id, settings, refresh_repo)


@router.post("/auth/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    response: Response,
    user_repo: UserRepositoryDep,
    refresh_repo: RefreshTokenRepositoryDep,
    settings: SettingsDep,
) -> TokenResponse:
    doc = user_repo.get_by_email(body.email)
    if doc is None or not verify_password(body.password, doc["password_hash"]):
        # Same message either way — don't tell an attacker which part was wrong.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return _issue_tokens(response, str(doc["_id"]), settings, refresh_repo)


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    settings: SettingsDep,
    refresh_repo: RefreshTokenRepositoryDep,
) -> TokenResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing refresh token")

    payload = decode_token(token, settings.jwt_secret_key, expected_type="refresh")
    if not refresh_repo.is_valid(payload["jti"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token revoked or unknown")

    # Rotate: the old refresh token is single-use.
    refresh_repo.revoke(payload["jti"])
    return _issue_tokens(response, payload["sub"], settings, refresh_repo)


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    settings: SettingsDep,
    refresh_repo: RefreshTokenRepositoryDep,
) -> dict[str, bool]:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        try:
            payload = decode_token(token, settings.jwt_secret_key, expected_type="refresh")
            refresh_repo.revoke(payload["jti"])
        except HTTPException:
            pass  # already invalid/expired — logout still succeeds
    response.delete_cookie(REFRESH_COOKIE)
    return {"success": True}


@router.get("/auth/me", response_model=UserPublic)
def me(user: Annotated[UserPublic, Depends(current_user)]) -> UserPublic:
    return user
