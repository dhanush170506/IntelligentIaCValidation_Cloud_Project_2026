import logging
import os
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .database.connection import check_database_connection, close_mongo_connection
from .routes.validation import router as validation_router
from .routes.reports import router as reports_router
from .routes.history import router as history_router
from .routes.dashboard import router as dashboard_router
from .routes.dataset_evaluation import router as dataset_evaluation_router


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _get_cors_origins() -> List[str]:
    origins = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in origins.split(",") if origin.strip()]


APP_NAME = os.getenv("APP_NAME", "Intelligent IaC Validation Backend")
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_mongo_connection()


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(validation_router)
app.include_router(reports_router)
app.include_router(history_router)
app.include_router(dashboard_router)
app.include_router(dataset_evaluation_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": exc.detail},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled backend error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal server error"},
    )


@app.get("/health")
async def health_check() -> dict:
    return {
        "success": True,
        "message": "Backend is running",
        "service": APP_NAME,
        "version": APP_VERSION,
    }


@app.get("/health/database")
async def database_health_check():
    database_status = check_database_connection()

    if not database_status["success"]:
        return JSONResponse(status_code=503, content=database_status)

    return database_status
