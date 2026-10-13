from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from app.core.compliance import Role
from app.models.base import APIModel


class SignupRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=8)
    # Self-declared, not verified: it only selects how loud the "not legal
    # advice" disclaimer is, never what a user is allowed to do.
    role: Role
    # DPDP: consent must be an affirmative act. Literal[True] makes a missing
    # or false value a 422 rather than a silently-recorded non-consent.
    consent: Literal[True]


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
    role: Role


class DeleteAccountRequest(APIModel):
    # Re-confirming the password guards against a leaked short-lived access
    # token being enough on its own to trigger an irreversible deletion.
    password: str


class DeleteAccountResponse(APIModel):
    success: bool
