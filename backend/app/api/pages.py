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

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


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
