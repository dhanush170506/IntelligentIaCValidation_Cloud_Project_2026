import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pymongo.errors import PyMongoError

from ..database.connection import get_database

logger = logging.getLogger(__name__)

router = APIRouter()

SUMMARY_FIELDS = {
    "_id": 0,
    "report_id": 1,
    "upload_id": 1,
    "filename": 1,
    "file_type": 1,
    "status": 1,
    "security_score": 1,
    "drift_score": 1,
    "confidence": 1,
    "created_at": 1,
}


def _serialize_summary(report: dict) -> dict:
    """Convert a MongoDB document to a JSON-safe summary dict."""
    for key, value in report.items():
        if isinstance(value, datetime):
            report[key] = value.isoformat()
    return report


@router.get("/history")
async def get_validation_history(
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
):
    """Retrieve a list of previous validation reports, newest first."""
    try:
        db = get_database()
        query = {}
        if status:
            query["status"] = status

        cursor = (
            db["validation_reports"]
            .find(query, SUMMARY_FIELDS)
            .sort("created_at", -1)
            .limit(limit)
        )

        reports: List[dict] = [_serialize_summary(doc) for doc in cursor]

        return {
            "success": True,
            "count": len(reports),
            "reports": reports,
        }

    except PyMongoError as exc:
        logger.error("Database error retrieving history: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable: {exc}",
        ) from exc
