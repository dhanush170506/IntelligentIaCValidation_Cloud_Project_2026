import os
from typing import Dict, List, Optional

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError


MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "iac_validation_db")
COLLECTION_NAMES: List[str] = [
    "users",
    "projects",
    "uploads",
    "validation_reports",
]

_client: Optional[MongoClient] = None


def get_mongo_client() -> MongoClient:
    global _client

    if _client is None:
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=3000)

    return _client


def get_database() -> Database:
    return get_mongo_client()[MONGODB_DATABASE]


def ensure_collections() -> None:
    database = get_database()
    existing_collections = set(database.list_collection_names())

    for collection_name in COLLECTION_NAMES:
        if collection_name not in existing_collections:
            database.create_collection(collection_name)


def check_database_connection() -> Dict[str, object]:
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        ensure_collections()

        return {
            "success": True,
            "message": "MongoDB connection successful",
            "database": MONGODB_DATABASE,
            "collections": COLLECTION_NAMES,
        }
    except (ServerSelectionTimeoutError, PyMongoError) as exc:
        return {
            "success": False,
            "message": "MongoDB connection failed",
            "error": str(exc),
        }


def close_mongo_connection() -> None:
    global _client

    if _client is not None:
        _client.close()
        _client = None
