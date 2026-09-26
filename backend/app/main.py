from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from qdrant_client import QdrantClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import auth, chat, health, pages, sessions
from app.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import limiter
from app.corpora.crosswalk import load_crosswalk
from app.corpora.registry import load_registry
from app.llm.factory import build_llm_provider
from app.repositories.chat_repository import ChatRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository

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
    app.state.user_repository = UserRepository(db)
    app.state.refresh_token_repository = RefreshTokenRepository(db)
    logger.info("connected_to_mongo")

    # D017 (closed): ingestion is no longer part of app startup at all — it
    # runs as its own CLI (scripts/ingest.py). Startup only connects to
    # collections that ingest.py already built, and fails readiness (not a
    # hard crash) if an enabled corpus's collection is missing.
    app.state.qdrant = QdrantClient(url=settings.qdrant_url)
    app.state.corpus_registry = registry = load_registry()
    app.state.corpus_ready = {}
    for corpus in registry.enabled():
        exists = app.state.qdrant.collection_exists(corpus.collection)
        app.state.corpus_ready[corpus.id] = exists
        if not exists:
            logger.error(
                "corpus_collection_missing", corpus=corpus.id, collection=corpus.collection
            )

    app.state.llm_provider = build_llm_provider(settings)
    app.state.crosswalk = load_crosswalk()
    logger.info("startup_complete")

    yield

    mongo_client.close()


def create_app() -> FastAPI:
    app = FastAPI(title="JurisAI", lifespan=lifespan)

    # D013: still all origins, matching legacy `CORS(app)` — tightened in Sprint 4
    # once there's a real frontend origin to scope it to via settings.cors_origins.
    # Not a blocker for the cookie-based refresh flow below: the login page is
    # served same-origin by this app until Sprint 5 introduces a separate origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)

    app.include_router(health.router)
    app.include_router(pages.router)
    app.include_router(auth.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    return app


app = create_app()
