"""Ported from jurisai/Backend/app.py (`/history`, `/session`, `/rename_session`,
`/delete_session`, `/logout`).

Now requires auth and scopes every query by user_id (D004-D008, closed) — a
session that isn't yours matches nothing in the repository layer, so these
routes return 404 rather than leaking whether the session_id exists at all.

Still open, tracked for Sprint 4:
- D014: exception text still reaches the client via `detail`.
- D026: renaming to the same title reports 404 instead of success, since
  `modified_count` is 0 on a no-op update.
- D028: no `$sort` after the `$group` in history.
"""

from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.security import CurrentUser
from app.deps import ChatRepositoryDep
from app.models.chat import DeleteRequest, RenameRequest, SessionSummary, SessionTurn

router = APIRouter()


@router.get("/history", response_model=list[SessionSummary])
def history(user: CurrentUser, chat_repo: ChatRepositoryDep) -> list[SessionSummary]:
    try:
        return [SessionSummary(**s) for s in chat_repo.get_history(user.id)]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/session/{session_id}", response_model=list[SessionTurn])
def get_session(
    session_id: str, user: CurrentUser, chat_repo: ChatRepositoryDep
) -> list[SessionTurn]:
    try:
        return [SessionTurn(**t) for t in chat_repo.get_session(user.id, session_id)]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/rename_session/{session_id}")
def rename_session(
    session_id: str, body: RenameRequest, user: CurrentUser, chat_repo: ChatRepositoryDep
) -> dict[str, Any]:
    new_title = body.title.strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="No title provided")
    try:
        if chat_repo.rename_session(user.id, session_id, new_title):
            return {"success": True}
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/delete_session")
def delete_session(
    body: DeleteRequest, user: CurrentUser, chat_repo: ChatRepositoryDep
) -> dict[str, Any]:
    try:
        if chat_repo.delete_session(user.id, body.session_id):
            return {"status": "success"}
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
