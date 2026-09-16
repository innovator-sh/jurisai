"""Rate limiting for D015 (no limit on the paid LLM route — anyone could burn
the whole LLM budget). Keyed by user where possible, falling back to IP for
unauthenticated requests (401 happens separately; this key is only used to
decide *whose* bucket a request counts against).

The JWT here is decoded without signature verification — this function only
picks a bucket key, it is not a security boundary. `current_user` still does
the real, verified check.
"""

import jwt
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


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
