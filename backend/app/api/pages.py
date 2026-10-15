"""Page serving for the Sprint 5 frontend rebuild. Every route here just
renders a template — auth is enforced client-side (each page's JS calls
POST /api/auth/refresh on load and redirects to /login on failure), the same
posture the legacy Flask app had. None of these routes render model- or
user-controlled content directly (that's chat.js's job, via
marked+DOMPurify — see static/vendor/), so none of them is a D009-D011 XSS
candidate.

firform.html is deliberately not served yet -- the FIR feature (backend +
form) is blocked pending real-world field/workflow requirements (see the
sprint plan). /templates' "File an FIR" card is shown disabled instead of
linking to a half-built page.
"""

from pathlib import Path
from typing import cast

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.config import Settings
from app.core.compliance import CONSENT_VERSION, SECURITY_LOG_RETENTION_DAYS

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# Who actually receives a user's question text, named plainly on /privacy
# (DPDP: disclose recipients). Unknown providers fall back to the raw id.
_LLM_PROVIDER_DISCLOSURE = {
    "groq": "Groq, Inc. (United States)",
    "mistral": "Mistral AI (France)",
    "anthropic": "Anthropic, PBC (United States)",
    "bedrock": "Amazon Web Services",
}


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html")


@router.get("/", response_class=HTMLResponse)
def chat_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"active_view": "chat"})


@router.get("/templates", response_class=HTMLResponse)
def legal_templates_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "legal.html", {"active_view": "templates"})


@router.get("/account", response_class=HTMLResponse)
def account_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "account.html", {"active_view": "account"})


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "settings.html", {"active_view": "settings"})


@router.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request) -> HTMLResponse:
    settings = cast(Settings, request.app.state.settings)
    return templates.TemplateResponse(
        request,
        "privacy.html",
        {
            "consent_version": CONSENT_VERSION,
            "llm_provider_name": _LLM_PROVIDER_DISCLOSURE.get(
                settings.llm_provider, settings.llm_provider
            ),
            "retention_days": settings.chat_retention_days,
            "backup_days": settings.backup_retention_days,
            "security_log_days": SECURITY_LOG_RETENTION_DAYS,
            "grievance_name": settings.grievance_officer_name,
            "grievance_email": settings.grievance_officer_email,
            "grievance_address": settings.grievance_officer_address,
        },
    )
