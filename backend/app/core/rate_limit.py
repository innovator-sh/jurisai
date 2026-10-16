"""Rate limiting for D015 (no limit on the paid LLM route — anyone could burn
the whole LLM budget). Keyed by user where possible, falling back to IP for
unauthenticated requests (401 happens separately; this key is only used to
decide *whose* bucket a request counts against).

The JWT here is decoded without signature verification — this function only
picks a bucket key, it is not a security boundary. `current_user` still does
the real, verified check.
"""

import jwt
from fastapi import Request, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.security_log import audit


def user_or_ip_key(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.removeprefix("Bearer ").strip()
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except jwt.PyJWTError:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=user_or_ip_key)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """slowapi's stock 429 response, plus a security-log entry (CERT-In)."""
    audit("rate_limited", request=request, path=request.url.path)
    return _rate_limit_exceeded_handler(request, exc)
