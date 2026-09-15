from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient

from app.api import chat, health, sessions
from app.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.rag.ingest import build_or_load_vector_store
from app.repositories.chat_repository import ChatRepository

# Read at import time, not first request — mirrors Flask's top-level execution,
# which failed immediately on a missing var rather than on first use.
settings: Settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.settings = settings

    mongo_client: MongoClient[dict[str, Any]] = MongoClient(settings.mongo_uri)
    db = mongo_client["jurisai"]
    app.state.chat_repository = ChatRepository(db)
    logger.info("connected_to_mongo")

    # Ported from Flask's import-time ingestion (D017, open, Sprint 3 moves this
    # to a decoupled `scripts/ingest.py` so a slow/failed ingest can't take the
    # whole app down at every restart). Lifespan is the FastAPI-idiomatic
    # equivalent of Flask's top-level module code, not a behaviour change.
    app.state.vector_store = build_or_load_vector_store()
    logger.info("startup_complete")

    yield

    mongo_client.close()


def create_app() -> FastAPI:
    app = FastAPI(title="JurisAI", lifespan=lifespan)

    # D013: still all origins, matching legacy `CORS(app)` — tightened in Sprint 4
    # once there's a real frontend origin to scope it to via settings.cors_origins.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    return app


app = create_app()
