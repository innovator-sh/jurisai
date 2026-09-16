from typing import Annotated, cast

from fastapi import Depends, Request
from langchain_community.vectorstores import Chroma

from app.config import Settings
from app.repositories.chat_repository import ChatRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_vector_store(request: Request) -> Chroma:
    return cast(Chroma, request.app.state.vector_store)


def get_chat_repository(request: Request) -> ChatRepository:
    return cast(ChatRepository, request.app.state.chat_repository)


def get_user_repository(request: Request) -> UserRepository:
    return cast(UserRepository, request.app.state.user_repository)


def get_refresh_token_repository(request: Request) -> RefreshTokenRepository:
    return cast(RefreshTokenRepository, request.app.state.refresh_token_repository)


SettingsDep = Annotated[Settings, Depends(get_settings)]
VectorStoreDep = Annotated[Chroma, Depends(get_vector_store)]
ChatRepositoryDep = Annotated[ChatRepository, Depends(get_chat_repository)]
UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
RefreshTokenRepositoryDep = Annotated[
    RefreshTokenRepository, Depends(get_refresh_token_repository)
]
