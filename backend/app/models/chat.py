from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


class SessionSummary(BaseModel):
    session_id: str
    title: str
    timestamp: datetime


class SessionTurn(BaseModel):
    query: str
    response: str
    timestamp: datetime


class RenameRequest(BaseModel):
    title: str


class DeleteRequest(BaseModel):
    session_id: str
