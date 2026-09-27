"""Global exception handlers — the single place a response body is built
for any error, so no route can accidentally leak an exception string (D014).
Every error response shares one shape: {"error": <message>, "request_id": <id>}.
The real exception (with traceback) is only ever logged server-side, keyed
by the same request id a client sees, so it's still traceable without ever
appearing in the response body.
"""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "request_id": _request_id(request)},
        headers=exc.headers,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_exception",
        request_id=_request_id(request),
        path=request.url.path,
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "request_id": _request_id(request)},
    )
