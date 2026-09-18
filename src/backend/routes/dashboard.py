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
    """Return aggregate statistics from validation reports and dataset evaluations."""
    try:
        db = get_database()
        validation_collection = db["validation_reports"]
        dataset_runs_collection = db["dataset_evaluation_runs"]

        total_validations = validation_collection.count_documents({})
        passed = validation_collection.count_documents({"status": "PASS"})
        failed = validation_collection.count_documents({"status": "FAIL"})
        review_required = validation_collection.count_documents({"status": "REVIEW_REQUIRED"})

        sec_pipeline = [
            {"$match": {"security_score": {"$type": "number"}}},
            {"$group": {"_id": None, "avg": {"$avg": "$security_score"}}},
        ]
        sec_result = list(validation_collection.aggregate(sec_pipeline))
        average_security_score = round(sec_result[0]["avg"], 1) if sec_result else None

        drift_pipeline = [
            {"$match": {"drift_score": {"$type": "number"}}},
            {"$group": {"_id": None, "avg": {"$avg": "$drift_score"}}},
        ]
        drift_result = list(validation_collection.aggregate(drift_pipeline))
        average_drift_score = round(drift_result[0]["avg"], 1) if drift_result else None

        confidence_pipeline = [
            {"$match": {"confidence": {"$type": "number"}}},
            {"$group": {"_id": None, "avg": {"$avg": "$confidence"}}},
        ]
        confidence_result = list(validation_collection.aggregate(confidence_pipeline))
        average_confidence = round(confidence_result[0]["avg"], 4) if confidence_result else None

        dataset_runs = list(
            dataset_runs_collection.find({}, {"_id": 0, "run_id": 1, "dataset_name": 1, "status": 1, "samples_processed": 1, "aggregate_metrics": 1, "started_at": 1, "completed_at": 1})
            .sort("started_at", -1)
            .limit(10)
        )
        for run in dataset_runs:
            for key, value in list(run.items()):
                if isinstance(value, datetime):
                    run[key] = value.isoformat()

        dataset_evaluations = dataset_runs_collection.count_documents({})
        total_samples_processed = sum(int(run.get("samples_processed") or 0) for run in dataset_runs)
        validation_distribution = {
            "pass": passed,
            "fail": failed,
            "review_required": review_required,
        }

        recent_cursor = (
            validation_collection.find({}, RECENT_FIELDS)
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
            "average_confidence": average_confidence,
            "total_dataset_evaluations": dataset_evaluations,
            "total_samples_processed": total_samples_processed,
            "validation_distribution": validation_distribution,
            "recent_validations": recent_validations,
            "recent_dataset_runs": dataset_runs,
        }

    except PyMongoError as exc:
        logger.error("Database error retrieving dashboard summary: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable: {exc}",
        ) from exc
