from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pymongo.errors import PyMongoError

from ..database.connection import get_database
from ..services.dataset_evaluation_service import (
    aggregate_dataset_results,
    default_dataset_catalog,
    discover_dataset_samples,
    evaluate_dataset_samples,
)

router = APIRouter()

DATASET_RUN_STATUS = {"queued": "queued", "running": "running", "completed": "completed", "failed": "failed"}


def _serialize_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def _run_dataset_evaluation(run_id: str, dataset_name: str, sample_count: int) -> None:
    db = get_database()
    started_at = datetime.now(timezone.utc)
    sample_catalog = discover_dataset_samples(dataset_name=dataset_name, max_samples=sample_count)

    try:
        db["dataset_evaluation_runs"].update_one(
            {"run_id": run_id},
            {"$set": {
                "run_id": run_id,
                "dataset_name": dataset_name,
                "started_at": started_at,
                "completed_at": None,
                "status": "running",
                "samples_requested": len(sample_catalog),
                "samples_processed": 0,
                "successful_samples": 0,
                "failed_samples": 0,
                "aggregate_metrics": {},
                "configuration": {"sample_count": sample_count, "max_samples": sample_count},
                "errors": [],
            }},
            upsert=True,
        )

        results = evaluate_dataset_samples(sample_catalog, dataset_name=dataset_name, max_samples=sample_count)
        aggregate = aggregate_dataset_results(results)

        db["dataset_evaluation_results"].delete_many({"run_id": run_id})
        for item in results:
            db["dataset_evaluation_results"].insert_one({
                "run_id": run_id,
                "sample_id": item.get("sample_id"),
                "dataset_name": item.get("dataset_name") or dataset_name,
                "filename": item.get("filename"),
                "relative_path": item.get("relative_path"),
                "file_type": item.get("file_type"),
                "status": item.get("status"),
                "security_score": item.get("security_score"),
                "drift_score": item.get("drift_score"),
                "confidence": item.get("confidence"),
                "findings": item.get("findings", []),
                "recommendations": item.get("recommendations", []),
                "processing_time_ms": item.get("processing_time_ms"),
                "ground_truth": item.get("ground_truth"),
                "evaluation_metrics": item.get("evaluation_metrics", {}),
                "errors": item.get("errors", []),
                "warnings": item.get("warnings", []),
                "sample_path": item.get("path"),
                "source": item.get("source"),
            })

        completed_at = datetime.now(timezone.utc)
        db["dataset_evaluation_runs"].update_one(
            {"run_id": run_id},
            {"$set": {
                "completed_at": completed_at,
                "status": "completed",
                "samples_processed": len(results),
                "successful_samples": aggregate.get("successful_samples", 0),
                "failed_samples": aggregate.get("failed_samples", 0),
                "aggregate_metrics": aggregate,
                "errors": [],
            }},
            upsert=True,
        )
    except Exception as exc:  # pragma: no cover -runtime guard for the background task
        db["dataset_evaluation_runs"].update_one(
            {"run_id": run_id},
            {"$set": {
                "completed_at": datetime.now(timezone.utc),
                "status": "failed",
                "errors": [str(exc)],
            }},
            upsert=True,
        )


@router.post("/dataset-evaluations")
async def start_dataset_evaluation(request: Request):
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    body = body or {}
    dataset_name = body.get("dataset_name") or "terragoat-master"
    sample_count = int(body.get("sample_count") or body.get("max_samples") or os.getenv("DATASET_MAX_SAMPLES", "20"))
    if sample_count <= 0:
        sample_count = 1

    run_id = str(uuid.uuid4())
    db = get_database()
    run_document = {
        "run_id": run_id,
        "dataset_name": dataset_name,
        "started_at": datetime.now(timezone.utc),
        "completed_at": None,
        "status": "queued",
        "samples_requested": sample_count,
        "samples_processed": 0,
        "successful_samples": 0,
        "failed_samples": 0,
        "aggregate_metrics": {},
        "configuration": {"dataset_name": dataset_name, "sample_count": sample_count},
        "errors": [],
    }
    db["dataset_evaluation_runs"].insert_one(run_document)
    asyncio.create_task(_run_dataset_evaluation(run_id, dataset_name, sample_count))
    return {"success": True, "run_id": run_id, "status": "queued"}


@router.get("/dataset-evaluations")
async def list_dataset_evaluations():
    try:
        db = get_database()
        runs = list(db["dataset_evaluation_runs"].find({}, {"_id": 0}).sort("started_at", -1).limit(20))
        for run in runs:
            for key, value in list(run.items()):
                if isinstance(value, datetime):
                    run[key] = value.isoformat()
        return {
            "success": True,
            "count": len(runs),
            "runs": runs,
            "available_datasets": [
                {"name": name, "count": len(samples)}
                for name, samples in default_dataset_catalog().items()
            ],
        }
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc


@router.get("/dataset-evaluations/{run_id}")
async def get_dataset_evaluation(run_id: str):
    try:
        db = get_database()
        run = db["dataset_evaluation_runs"].find_one({"run_id": run_id}, {"_id": 0})
        if run is None:
            raise HTTPException(status_code=404, detail=f"Dataset evaluation run not found: {run_id}")
        for key, value in list(run.items()):
            if isinstance(value, datetime):
                run[key] = value.isoformat()
        return {"success": True, "run": run}
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc


@router.get("/dataset-evaluations/{run_id}/results")
async def get_dataset_evaluation_results(run_id: str):
    try:
        db = get_database()
        rows = list(db["dataset_evaluation_results"].find({"run_id": run_id}, {"_id": 0}).sort("sample_id", 1))
        return {"success": True, "count": len(rows), "results": rows}
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc
