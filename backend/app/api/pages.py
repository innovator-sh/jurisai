"""Minimal page serving — just enough for Sprint 2's real signup/login to have
somewhere to live. Not the frontend rebuild: that's Sprint 5's job (base.html,
the other five pages, the visual identity from index.css). One page, plain
markup, no framework, textContent-only rendering (nothing here is a candidate
for the D009-D011 XSS pattern since there's no model or user-controlled
content rendered on this page at all).
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
