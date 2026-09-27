"""Ported from jurisai/Backend/app.py, now scoped by user_id everywhere
(D004-D008, Sprint 2) — a session that isn't yours matches nothing, so every
route built on this returns 404 rather than leaking whether it exists.
"""

from datetime import UTC, datetime
from typing import Any

from pymongo.collection import Collection
from pymongo.database import Database

DEFAULT_HISTORY_LIMIT = 50


class ChatRepository:
    def __init__(self, db: Database[dict[str, Any]]) -> None:
        self.collection: Collection[dict[str, Any]] = db["chat_history"]
        self.collection.create_index([("user_id", 1), ("session_id", 1)])

    def insert_turn(
        self,
        user_id: str,
        session_id: str,
        query: str,
        response: str,
        *,
        corpus: str,
        ingest_version: str,
    ) -> None:
        title = query[:50] + "..." if len(query) > 50 else query
        self.collection.insert_one(
            {
                "user_id": user_id,
                "session_id": session_id,
                "query": query,
                "response": response,
                "timestamp": datetime.now(UTC),
                "title": title,
                "corpus": corpus,
                "ingest_version": ingest_version,
            }
        )

    def get_history(
        self, user_id: str, limit: int = DEFAULT_HISTORY_LIMIT, skip: int = 0
    ) -> list[dict[str, Any]]:
        pipeline: list[dict[str, Any]] = [
            {"$match": {"user_id": user_id}},
            {"$sort": {"timestamp": 1}},
            {
                "$group": {
                    "_id": "$session_id",
                    "query": {"$first": "$query"},
                    "timestamp": {"$first": "$timestamp"},
                    "title": {"$first": "$title"},
                }
            },
            {"$sort": {"timestamp": -1}},
            {"$skip": skip},
            {"$limit": limit},
        ]
        sessions = list(self.collection.aggregate(pipeline))
        results = []
        for s in sessions:
            fallback_title = s["query"][:50] + "..." if len(s["query"]) > 50 else s["query"]
            results.append(
                {
                    "session_id": str(s["_id"]),
                    "title": s.get("title") or fallback_title,
                    "timestamp": s["timestamp"],
                }
            )
        return results

    def get_session(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        chats = self.collection.find(
            {"user_id": user_id, "session_id": session_id}
        ).sort("timestamp", 1)
        return [
            {
                "query": c["query"],
                "response": c["response"],
                "timestamp": c["timestamp"],
                "corpus": c.get("corpus"),
            }
            for c in chats
        ]

    def rename_session(self, user_id: str, session_id: str, new_title: str) -> bool:
        """True if the session exists and belongs to this user — regardless
        of whether the title actually changed. D026 (closed): renaming to
        the session's current title used to report 404, since MongoDB's
        `modified_count` is 0 on a no-op update; existence is now checked
        via `matched_count`, which is set even when nothing was modified."""
        result = self.collection.update_many(
            {"user_id": user_id, "session_id": session_id}, {"$set": {"title": new_title}}
        )
        return result.matched_count > 0

    def delete_session(self, user_id: str, session_id: str) -> bool:
        result = self.collection.delete_many({"user_id": user_id, "session_id": session_id})
        return result.deleted_count > 0
