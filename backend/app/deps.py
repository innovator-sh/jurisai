from typing import Annotated, cast

from fastapi import Depends, Request
from qdrant_client import QdrantClient

from app.config import Settings
from app.corpora.registry import CorpusRegistry
from app.llm.base import LLMProvider
from app.repositories.chat_repository import ChatRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_qdrant(request: Request) -> QdrantClient:
    return cast(QdrantClient, request.app.state.qdrant)


def get_corpus_registry(request: Request) -> CorpusRegistry:
    return cast(CorpusRegistry, request.app.state.corpus_registry)


def get_llm_provider(request: Request) -> LLMProvider:
    return cast(LLMProvider, request.app.state.llm_provider)


def get_chat_repository(request: Request) -> ChatRepository:
    return cast(ChatRepository, request.app.state.chat_repository)


def get_user_repository(request: Request) -> UserRepository:
    return cast(UserRepository, request.app.state.user_repository)


def get_refresh_token_repository(request: Request) -> RefreshTokenRepository:
    return cast(RefreshTokenRepository, request.app.state.refresh_token_repository)


SettingsDep = Annotated[Settings, Depends(get_settings)]
QdrantDep = Annotated[QdrantClient, Depends(get_qdrant)]
CorpusRegistryDep = Annotated[CorpusRegistry, Depends(get_corpus_registry)]
LLMProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]
ChatRepositoryDep = Annotated[ChatRepository, Depends(get_chat_repository)]
UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
RefreshTokenRepositoryDep = Annotated[
    RefreshTokenRepository, Depends(get_refresh_token_repository)
]
