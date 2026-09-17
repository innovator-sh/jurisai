from datetime import date, datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    # Corpus routing (Sprint 3's router.py); today only "ipc" is enabled, so
    # every value other than an explicit unrecognised one collapses to it —
    # see the plan's Query routing precedence.
    corpus_mode: str | None = None
    offence_date: date | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    corpus: str
    act: str


class SessionSummary(BaseModel):
    session_id: str
    title: str
    timestamp: datetime


class SessionTurn(BaseModel):
    query: str
    response: str
    timestamp: datetime
    corpus: str | None = None


class RenameRequest(BaseModel):
    title: str


class DeleteRequest(BaseModel):
    session_id: str
