import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, HTTPException, UploadFile
from pymongo.errors import PyMongoError

from ..database.connection import get_database
from ..services.ai_service import validate_iac

logger = logging.getLogger(__name__)


router = APIRouter()

BACKEND_DIR = Path(__file__).resolve().parents[1]
UPLOAD_DIR = BACKEND_DIR / "storage" / "uploads"
MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(5 * 1024 * 1024)))
CHUNK_SIZE_BYTES = 1024 * 1024

SUPPORTED_FILE_TYPES: Dict[str, str] = {
    ".tf": "terraform",
    ".yaml": "cloudformation",
    ".yml": "cloudformation",
}


def _get_file_type(filename: str) -> str:
    extension = Path(filename).suffix.lower()

    if extension not in SUPPORTED_FILE_TYPES:
        allowed_extensions = ", ".join(SUPPORTED_FILE_TYPES.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed extensions: {allowed_extensions}",
        )

    return SUPPORTED_FILE_TYPES[extension]


@router.post("/validate")
async def upload_iac_file(file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file must be uploaded")

    file_type = _get_file_type(file.filename)
    upload_id = str(uuid.uuid4())
    original_filename = Path(file.filename).name
    stored_filename = f"{upload_id}{Path(original_filename).suffix.lower()}"
    file_path = UPLOAD_DIR / stored_filename
    file_size = 0
    file_content = b""

    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        with file_path.open("wb") as stored_file:
            while chunk := await file.read(CHUNK_SIZE_BYTES):
                file_size += len(chunk)

                if file_size > MAX_UPLOAD_SIZE_BYTES:
                    stored_file.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File is too large. Maximum size is {MAX_UPLOAD_SIZE_BYTES} bytes",
                    )

                stored_file.write(chunk)
                file_content += chunk

        if file_size == 0:
            file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Empty files are not allowed")

        metadata = {
            "upload_id": upload_id,
            "filename": original_filename,
            "file_type": file_type,
            "file_path": str(file_path),
            "file_size": file_size,
            "uploaded_at": datetime.now(timezone.utc),
            "status": "uploaded",
        }

        get_database()["uploads"].insert_one(metadata)

        # Unit 4: send content to AI engine for validation
        iac_content = file_content.decode("utf-8", errors="replace")
        ai_result = await validate_iac(
            upload_id=upload_id,
            filename=original_filename,
            file_type=file_type,
            content=iac_content,
        )

        # Unit 5: store the validation report in MongoDB
        report_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        validation_report = {
            "report_id": report_id,
            "upload_id": upload_id,
            "filename": original_filename,
            "file_type": file_type,
            "status": ai_result.get("status", "ERROR"),
            "security_score": ai_result.get("security_score"),
            "drift_score": ai_result.get("drift_score"),
            "confidence": ai_result.get("confidence"),
            "findings": ai_result.get("findings", []),
            "recommendations": ai_result.get("recommendations", []),
            "created_at": now,
        }

        # Preserve the full AI response for debugging / future use
        if ai_result.get("status") == "ERROR":
            validation_report["error_detail"] = ai_result.get("error")

        try:
            db = get_database()
            db["validation_reports"].insert_one(validation_report)

            # Update upload status to reflect validation completion
            db["uploads"].update_one(
                {"upload_id": upload_id},
                {"$set": {
                    "status": "validated",
                    "report_id": report_id,
                    "validated_at": now,
                }},
            )
        except PyMongoError as exc:
            logger.error("Failed to store validation report: %s", exc)
            return {
                "success": False,
                "upload_id": upload_id,
                "filename": original_filename,
                "file_type": file_type,
                "status": "uploaded",
                "validation": ai_result,
                "report_storage_error": f"Report could not be stored in MongoDB: {exc}",
            }

        return {
            "success": True,
            "upload_id": upload_id,
            "report_id": report_id,
            "filename": original_filename,
            "file_type": file_type,
            "status": "validated",
            "validation": ai_result,
        }
    except HTTPException:
        raise
    except PyMongoError as exc:
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=503,
            detail=f"File uploaded locally, but MongoDB metadata storage failed: {exc}",
        ) from exc
    except OSError as exc:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"File upload failed: {exc}") from exc
    finally:
        await file.close()
