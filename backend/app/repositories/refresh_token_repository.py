from datetime import datetime
from typing import Any

from pymongo.collection import Collection
from pymongo.database import Database


class RefreshTokenRepository:
    """Tracks issued refresh tokens by jti so logout can actually revoke one —
    a JWT alone can't be invalidated before its natural expiry."""

    def __init__(self, db: Database[dict[str, Any]]) -> None:
        self.collection: Collection[dict[str, Any]] = db["refresh_tokens"]
        self.collection.create_index("jti", unique=True)
        self.collection.create_index("expires_at", expireAfterSeconds=0)

    def store(self, jti: str, user_id: str, expires_at: datetime) -> None:
        self.collection.insert_one(
            {"jti": jti, "user_id": user_id, "expires_at": expires_at, "revoked": False}
        )

    def is_valid(self, jti: str) -> bool:
        doc = self.collection.find_one({"jti": jti})
        return doc is not None and not doc["revoked"]

    def revoke(self, jti: str) -> None:
        self.collection.update_one({"jti": jti}, {"$set": {"revoked": True}})

    def delete_all_for_user(self, user_id: str) -> None:
        """DPDP account-deletion support -- a real purge (not just marking
        revoked), since the account itself is going away. See
        api/auth.py's delete_account."""
        self.collection.delete_many({"user_id": user_id})
