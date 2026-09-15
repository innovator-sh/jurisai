"""Liveness now; real dependency checks (Mongo/vector store/LLM provider
reachability) on /readyz are Sprint 4 work — this is a placeholder that
always succeeds so the route exists for Docker/CI healthchecks today."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict[str, str]:
    return {"status": "ok"}
