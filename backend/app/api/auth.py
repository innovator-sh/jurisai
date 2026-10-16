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

from app.core.compliance import CONSENT_VERSION
from app.core.security import (
    REFRESH_TOKEN_TTL,
    create_access_token,
    create_refresh_token,
    current_user,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.security_log import audit, email_fingerprint
from app.deps import (
    ChatRepositoryDep,
    RefreshTokenRepositoryDep,
    SettingsDep,
    UserRepositoryDep,
)
from app.models.user import (
    DeleteAccountRequest,
    DeleteAccountResponse,
    LoginRequest,
    SignupRequest,
    TokenResponse,
    UserPublic,
)
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
        secure=settings.cookie_secure,
        max_age=int(REFRESH_TOKEN_TTL.total_seconds()),
    )
    return TokenResponse(access_token=access_token)


@router.post("/auth/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(
    request: Request,
    body: SignupRequest,
    response: Response,
    user_repo: UserRepositoryDep,
    refresh_repo: RefreshTokenRepositoryDep,
    settings: SettingsDep,
) -> TokenResponse:
    try:
        user = user_repo.create(
            body.email, hash_password(body.password), body.role, CONSENT_VERSION
        )
    except EmailAlreadyRegistered as e:
        audit(
            "signup_rejected_duplicate",
            request=request,
            email_hash=email_fingerprint(body.email),
        )
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from e
    audit(
        "signup",
        request=request,
        user_id=user.id,
        role=body.role,
        consent_version=CONSENT_VERSION,
    )
    return _issue_tokens(response, user.id, settings, refresh_repo)


@router.post("/auth/login", response_model=TokenResponse)
def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    user_repo: UserRepositoryDep,
    refresh_repo: RefreshTokenRepositoryDep,
    settings: SettingsDep,
) -> TokenResponse:
    doc = user_repo.get_by_email(body.email)
    if doc is None or not verify_password(body.password, doc["password_hash"]):
        audit("login_failed", request=request, email_hash=email_fingerprint(body.email))
        # Same message either way — don't tell an attacker which part was wrong.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    audit("login_success", request=request, user_id=str(doc["_id"]))
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
        # A revoked/unknown token being presented is the signature of a
        # replayed (possibly stolen) refresh token -- worth a security event.
        audit("refresh_rejected", request=request, user_id=payload["sub"])
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token revoked or unknown")

    # Rotate: the old refresh token is single-use.
    refresh_repo.revoke(payload["jti"])
    audit("token_refresh", request=request, user_id=payload["sub"])
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
            audit("logout", request=request, user_id=payload["sub"])
        except HTTPException:
            pass  # already invalid/expired — logout still succeeds
    response.delete_cookie(REFRESH_COOKIE)
    return {"success": True}


@router.get("/auth/me", response_model=UserPublic)
def me(user: Annotated[UserPublic, Depends(current_user)]) -> UserPublic:
    return user


@router.post("/auth/delete_account", response_model=DeleteAccountResponse)
def delete_account(
    request: Request,
    body: DeleteAccountRequest,
    response: Response,
    user: Annotated[UserPublic, Depends(current_user)],
    user_repo: UserRepositoryDep,
    chat_repo: ChatRepositoryDep,
    refresh_repo: RefreshTokenRepositoryDep,
) -> DeleteAccountResponse:
    """DPDP-required real account deletion -- purges chat history and
    revoked refresh tokens, not a soft flag (D059). Requires re-confirming
    the password: the access token alone (short-lived, but still a bearer
    credential) shouldn't be sufficient on its own to trigger something
    this irreversible."""
    doc = user_repo.get_by_email(user.email)
    if doc is None or not verify_password(body.password, doc["password_hash"]):
        audit("account_delete_rejected", request=request, user_id=user.id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid password")

    chat_repo.delete_all_for_user(user.id)
    refresh_repo.delete_all_for_user(user.id)
    user_repo.delete(user.id)
    audit("account_deleted", request=request, user_id=user.id)
    response.delete_cookie(REFRESH_COOKIE)
    return DeleteAccountResponse(success=True)
