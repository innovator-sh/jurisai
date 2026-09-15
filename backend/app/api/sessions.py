"""Ported from jurisai/Backend/app.py (`/history`, `/session`, `/rename_session`,
`/delete_session`, `/logout`), relocated only.

Preserved as-is, all tracked as open issues for later sprints:
- D004-D008: no auth, no user_id filter anywhere — any session_id is readable,
  renameable, and deletable by anyone who has or guesses it (Sprint 2).
- D014: exception text reaches the client via `detail` (Sprint 4).
- D026: renaming to the same title reports 404 instead of success, since
  `modified_count` is 0 on a no-op update (Sprint 4).
- D028: no `$sort` after the `$group` in history, so ordering isn't guaranteed
  (Sprint 4).
"""

from typing import Any

from fastapi import APIRouter, HTTPException

from app.deps import ChatRepositoryDep
from app.models.chat import DeleteRequest, RenameRequest, SessionSummary, SessionTurn

router = APIRouter()


@router.get("/history", response_model=list[SessionSummary])
def history(chat_repo: ChatRepositoryDep) -> list[SessionSummary]:
    try:
        return [SessionSummary(**s) for s in chat_repo.get_history()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/session/{session_id}", response_model=list[SessionTurn])
def get_session(session_id: str, chat_repo: ChatRepositoryDep) -> list[SessionTurn]:
    try:
        return [SessionTurn(**t) for t in chat_repo.get_session(session_id)]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/rename_session/{session_id}")
def rename_session(
    session_id: str, body: RenameRequest, chat_repo: ChatRepositoryDep
) -> dict[str, Any]:
    new_title = body.title.strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="No title provided")
    try:
        if chat_repo.rename_session(session_id, new_title):
            return {"success": True}
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/delete_session")
def delete_session(body: DeleteRequest, chat_repo: ChatRepositoryDep) -> dict[str, Any]:
    try:
        if chat_repo.delete_session(body.session_id):
            return {"status": "success"}
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/logout")
def logout() -> dict[str, Any]:
    return {"redirect": "/login"}
