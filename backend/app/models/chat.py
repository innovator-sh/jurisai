from datetime import date, datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    # Corpus routing (rag/router.py) — see the plan's Query routing
    # precedence. corpus_mode="ipc"/"bns" pins one explicitly; omitted with
    # no offence_date and no in-query citation defaults to hybrid (both).
    corpus_mode: str | None = None
    offence_date: date | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    corpus: str  # a corpus id, or "hybrid" when more than one was used
    acts: list[str]  # every act actually cited from, primary corpus first


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
