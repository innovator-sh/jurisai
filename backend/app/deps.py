from typing import Annotated, cast

from fastapi import Depends, Request
from langchain_community.vectorstores import Chroma

from app.config import Settings
from app.repositories.chat_repository import ChatRepository


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_vector_store(request: Request) -> Chroma:
    return cast(Chroma, request.app.state.vector_store)


def get_chat_repository(request: Request) -> ChatRepository:
    return cast(ChatRepository, request.app.state.chat_repository)


SettingsDep = Annotated[Settings, Depends(get_settings)]
VectorStoreDep = Annotated[Chroma, Depends(get_vector_store)]
ChatRepositoryDep = Annotated[ChatRepository, Depends(get_chat_repository)]
