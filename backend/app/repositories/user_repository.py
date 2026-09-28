from datetime import UTC, datetime
from typing import Any

from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from app.models.user import UserPublic


class EmailAlreadyRegistered(Exception):
    pass


class UserRepository:
    def __init__(self, db: Database[dict[str, Any]]) -> None:
        self.collection: Collection[dict[str, Any]] = db["users"]
        self.collection.create_index("email", unique=True)

    def create(self, email: str, password_hash: str) -> UserPublic:
        doc: dict[str, Any] = {
            "email": email,
            "password_hash": password_hash,
            "created_at": datetime.now(UTC),
        }
        try:
            result = self.collection.insert_one(doc)
        except DuplicateKeyError as e:
            raise EmailAlreadyRegistered(email) from e
        return UserPublic(id=str(result.inserted_id), email=email, created_at=doc["created_at"])

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        return self.collection.find_one({"email": email})

    def get_by_id(self, user_id: str) -> UserPublic | None:
        from bson import ObjectId
        from bson.errors import InvalidId

        try:
            oid = ObjectId(user_id)
        except InvalidId:
            return None
        doc = self.collection.find_one({"_id": oid})
        if doc is None:
            return None
        return UserPublic(id=str(doc["_id"]), email=doc["email"], created_at=doc["created_at"])

    def delete(self, user_id: str) -> bool:
        from bson import ObjectId
        from bson.errors import InvalidId

        try:
            oid = ObjectId(user_id)
        except InvalidId:
            return False
        result = self.collection.delete_one({"_id": oid})
        return result.deleted_count > 0
