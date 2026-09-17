import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pymongo.errors import PyMongoError

from ..database.connection import get_database

logger = logging.getLogger(__name__)

router = APIRouter()


def _serialize_report(report: dict) -> dict:
    """Convert a MongoDB document to a JSON-serializable dict.
    Drops the internal _id and ensures datetime fields are ISO strings.
    """
    report.pop("_id", None)

    for key, value in report.items():
        if isinstance(value, datetime):
            report[key] = value.isoformat()

    return report


@router.get("/reports/{report_id}")
async def get_report(report_id: str):
    """Retrieve a single validation report by its report_id."""
    try:
        db = get_database()
        report = db["validation_reports"].find_one(
            {"report_id": report_id},
            {"_id": 0},  # exclude MongoDB's _id
        )
    except PyMongoError as exc:
        logger.error("Database error retrieving report %s: %s", report_id, exc)
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable: {exc}",
        ) from exc

    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"Report not found: {report_id}",
        )

    return _serialize_report(report)
