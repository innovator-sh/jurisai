"""Baseline security response headers, applied to every response — JSON API
responses included, since a browser doesn't know the difference and these
are harmless there. `login.html` (api/pages.py) is the one HTML-rendering
route today; the CSP is scoped for it.

No HTTPS-redirect enforcement here on purpose: per the plan's Sprint 6
deploy design, TLS terminates at Caddy in front of this app, which runs
plain HTTP behind it — enforcing a redirect at this layer would conflict
with that (redirect loops without X-Forwarded-Proto handling) and would
break local `docker compose up` and the whole TestClient-based test suite,
both of which talk plain HTTP. HSTS is still sent, since it's meaningful
once TLS exists and harmless before it.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in _HEADERS.items():
            response.headers[name] = value
        return response
