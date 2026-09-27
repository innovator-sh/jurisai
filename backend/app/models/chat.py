from datetime import date, datetime

from app.models.base import APIModel


class ChatRequest(APIModel):
    query: str
    session_id: str | None = None
    # Corpus routing (rag/router.py) — see the plan's Query routing
    # precedence. corpus_mode="ipc"/"bns" pins one explicitly; omitted with
    # no offence_date and no in-query citation defaults to hybrid (both).
    corpus_mode: str | None = None
    offence_date: date | None = None


class CrosswalkFact(APIModel):
    """A single verified IPC<->BNS row grounding this answer, straight from
    the human-reviewed data/crosswalk/ipc_bns.csv — never LLM-inferred."""

    bns_section: str
    bns_title: str
    ipc_sections: list[str]
    ipc_titles: list[str]
    relation: str
    notes: str


class ChatResponse(APIModel):
    response: str
    session_id: str
    corpus: str  # a corpus id, or "hybrid" when more than one was used
    acts: list[str]  # every act actually cited from, primary corpus first
    crosswalk: list[CrosswalkFact] = []


class SessionSummary(APIModel):
    session_id: str
    title: str
    timestamp: datetime


class SessionTurn(APIModel):
    query: str
    response: str
    timestamp: datetime
    corpus: str | None = None


class RenameRequest(APIModel):
    title: str


class DeleteRequest(APIModel):
    session_id: str


class RenameSessionResponse(APIModel):
    success: bool


class DeleteSessionResponse(APIModel):
    status: str
