"""Ported from jurisai/Backend/app.py, relocated only — no behaviour change.

Known gaps, tracked as open issues and fixed in later sprints:
- No user_id filtering anywhere (D004-D008, Sprint 2) — any session_id can be read.
- No $sort after $group in get_history (D028, Sprint 4).
- No pagination on history (D008, Sprint 2).
"""

from datetime import UTC, datetime
from typing import Any

from pymongo.collection import Collection
from pymongo.database import Database


class ChatRepository:
    def __init__(self, db: Database[dict[str, Any]]) -> None:
        self.collection: Collection[dict[str, Any]] = db["chat_history"]
        self.collection.create_index("session_id")

    def insert_turn(self, session_id: str, query: str, response: str) -> None:
        title = query[:50] + "..." if len(query) > 50 else query
        self.collection.insert_one(
            {
                "session_id": session_id,
                "query": query,
                "response": response,
                "timestamp": datetime.now(UTC),
                "title": title,
            }
        )

    def get_history(self) -> list[dict[str, Any]]:
        pipeline: list[dict[str, Any]] = [
            {"$sort": {"timestamp": 1}},
            {
                "$group": {
                    "_id": "$session_id",
                    "query": {"$first": "$query"},
                    "timestamp": {"$first": "$timestamp"},
                    "title": {"$first": "$title"},
                }
            },
        ]
        sessions = list(self.collection.aggregate(pipeline))
        results = []
        for s in sessions:
            fallback_title = s["query"][:50] + "..." if len(s["query"]) > 50 else s["query"]
            results.append(
                {
                    "session_id": str(s["_id"]),
                    "title": s["title"] or fallback_title,
                    "timestamp": s["timestamp"],
                }
            )
        return results

    def get_session(self, session_id: str) -> list[dict[str, Any]]:
        chats = self.collection.find({"session_id": session_id}).sort("timestamp", 1)
        return [
            {"query": c["query"], "response": c["response"], "timestamp": c["timestamp"]}
            for c in chats
        ]

    def rename_session(self, session_id: str, new_title: str) -> bool:
        result = self.collection.update_many(
            {"session_id": session_id}, {"$set": {"title": new_title}}
        )
        return result.modified_count > 0

    def delete_session(self, session_id: str) -> bool:
        result = self.collection.delete_many({"session_id": session_id})
        return result.deleted_count > 0
