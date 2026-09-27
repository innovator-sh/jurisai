"""Liveness always succeeds. Readiness checks that every enabled corpus's
Qdrant collection actually exists, Mongo actually answers a ping, and (see
below) the configured LLM provider's key is present — this last one is
already guaranteed by `Settings` construction at startup (config.py's
`_require_selected_provider_key` fails fast before the app can even come
up), so it's reported here as a fact, not re-checked live."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.models.base import APIModel

router = APIRouter()


class HealthStatus(APIModel):
    status: str


@router.get("/healthz", response_model=HealthStatus)
def healthz() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/readyz")
def readyz(request: Request) -> JSONResponse:
    corpus_ready: dict[str, bool] = getattr(request.app.state, "corpus_ready", {})

    mongo_ok = True
    try:
        request.app.state.chat_repository.collection.database.client.admin.command("ping")
    except Exception:
        mongo_ok = False

    checks = {
        "corpora": corpus_ready,
        "mongo": mongo_ok,
        "llm_provider": True,  # guaranteed by Settings() at startup, see docstring
    }
    ready = all(corpus_ready.values()) and mongo_ok
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ok" if ready else "not ready", **checks},
    )
