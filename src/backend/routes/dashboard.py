import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pymongo.errors import PyMongoError

from ..database.connection import get_database

logger = logging.getLogger(__name__)

router = APIRouter()

RECENT_FIELDS = {
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


@router.get("/dashboard")
async def get_dashboard_summary():
    """Return aggregate statistics from validation_reports for the frontend dashboard."""
    try:
        db = get_database()
        collection = db["validation_reports"]

        total_validations = collection.count_documents({})

        passed = collection.count_documents({"status": "PASS"})
        failed = collection.count_documents({"status": "FAIL"})
        review_required = collection.count_documents({"status": "REVIEW_REQUIRED"})

        # Average security_score from documents where it's a valid number
        sec_pipeline = [
            {"$match": {"security_score": {"$type": "number"}}},
            {"$group": {"_id": None, "avg": {"$avg": "$security_score"}}},
        ]
        sec_result = list(collection.aggregate(sec_pipeline))
        average_security_score = (
            round(sec_result[0]["avg"], 1) if sec_result else 0
        )

        # Average drift_score from documents where it's a valid number
        drift_pipeline = [
            {"$match": {"drift_score": {"$type": "number"}}},
            {"$group": {"_id": None, "avg": {"$avg": "$drift_score"}}},
        ]
        drift_result = list(collection.aggregate(drift_pipeline))
        average_drift_score = (
            round(drift_result[0]["avg"], 1) if drift_result else 0
        )

        # 5 most recent validations
        recent_cursor = (
            collection.find({}, RECENT_FIELDS)
            .sort("created_at", -1)
            .limit(5)
        )
        recent_validations = [_serialize_summary(doc) for doc in recent_cursor]

        return {
            "total_validations": total_validations,
            "passed": passed,
            "failed": failed,
            "review_required": review_required,
            "average_security_score": average_security_score,
            "average_drift_score": average_drift_score,
            "recent_validations": recent_validations,
        }

    except PyMongoError as exc:
        logger.error("Database error retrieving dashboard summary: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable: {exc}",
        ) from exc
