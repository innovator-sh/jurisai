"""Liveness always succeeds. Readiness checks that every enabled corpus's
Qdrant collection actually exists (D017/item 2) — full dependency reachability
(Mongo, LLM provider) is Sprint 4's job, not duplicated here."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request) -> JSONResponse:
    corpus_ready: dict[str, bool] = getattr(request.app.state, "corpus_ready", {})
    if all(corpus_ready.values()):
        return JSONResponse(status_code=200, content={"status": "ok", "corpora": corpus_ready})
    return JSONResponse(status_code=503, content={"status": "not ready", "corpora": corpus_ready})
