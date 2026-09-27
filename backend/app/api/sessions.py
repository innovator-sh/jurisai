"""Ported from jurisai/Backend/app.py (`/history`, `/session`, `/rename_session`,
`/delete_session`, `/logout`).

Requires auth and scopes every query by user_id (D004-D008, closed) — a
session that isn't yours matches nothing in the repository layer, so these
routes return 404 rather than leaking whether the session_id exists at all.

D014 (closed): no route here builds its own error response anymore — an
unexpected exception propagates to core/errors.py's global handler, which
is what actually stops `str(e)` reaching the client (deleting the per-route
try/except was the fix, not patching each one's message).
D026 (closed): rename_session now checks existence separately from
modified_count — see ChatRepository.rename_session.
"""

from fastapi import APIRouter, HTTPException

from app.core.security import CurrentUser
from app.deps import ChatRepositoryDep
from app.models.chat import (
    DeleteRequest,
    DeleteSessionResponse,
    RenameRequest,
    RenameSessionResponse,
    SessionSummary,
    SessionTurn,
)

router = APIRouter()


@router.get("/history", response_model=list[SessionSummary])
def history(user: CurrentUser, chat_repo: ChatRepositoryDep) -> list[SessionSummary]:
    return [SessionSummary(**s) for s in chat_repo.get_history(user.id)]


@router.get("/session/{session_id}", response_model=list[SessionTurn])
def get_session(
    session_id: str, user: CurrentUser, chat_repo: ChatRepositoryDep
) -> list[SessionTurn]:
    return [SessionTurn(**t) for t in chat_repo.get_session(user.id, session_id)]


@router.post("/rename_session/{session_id}", response_model=RenameSessionResponse)
def rename_session(
    session_id: str, body: RenameRequest, user: CurrentUser, chat_repo: ChatRepositoryDep
) -> RenameSessionResponse:
    new_title = body.title.strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="No title provided")
    if chat_repo.rename_session(user.id, session_id, new_title):
        return RenameSessionResponse(success=True)
    raise HTTPException(status_code=404, detail="Session not found")


@router.post("/delete_session", response_model=DeleteSessionResponse)
def delete_session(
    body: DeleteRequest, user: CurrentUser, chat_repo: ChatRepositoryDep
) -> DeleteSessionResponse:
    if chat_repo.delete_session(user.id, body.session_id):
        return DeleteSessionResponse(status="success")
    raise HTTPException(status_code=404, detail="Session not found")
