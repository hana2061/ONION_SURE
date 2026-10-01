"""
FastAPI Backend Application Entrypoint
Smart India Hackathon 2026 - Problem Statement PS26031

AI-based Onion Quality Assessment and Deterministic Grading Platform
Features:
- Complete REST API routing under /api/v1
- Lifespan connection monitoring
- CORS and request logging middleware with request timing
- Standardized error handling
"""

import os
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import check_database_connection
from .api.routers import (
    health,
    auth,
    users,
    farmers,
    procurement_centres,
    lots,
    inspections,
    grading_policies,
    model_versions,
    reports,
    audit_logs,
    sync,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("onion_sure")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Verify database connection
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    try:
        db_ok = check_database_connection()
        if db_ok:
            from .database import engine
            from .database import SessionLocal
            from .seed import seed_database

            if engine.dialect.name == "sqlite":
                from .models.entities import Base as EntityBase
                EntityBase.metadata.create_all(bind=engine)
                logger.info("Local SQLite tables created/verified successfully.")

            _sdb = SessionLocal()
            try:
                seed_database(_sdb)
                logger.info("Database seed check completed successfully.")
            except Exception as _se:
                logger.warning(f"Database seed check: {_se}")
            finally:
                _sdb.close()

            logger.info("Database connection verified successfully.")
        else:
            logger.warning(
                "Database connection could not be established on startup. "
                "Ensure PostgreSQL is running via 'docker compose up -d' or DATABASE_URL is configured."
            )
    except Exception as e:
        logger.warning(f"Database check skipped during startup: {e}")
    yield
    # Shutdown
    logger.info("Shutting down application...")


app = FastAPI(
    title="ONION_SURE API",
    description="AI-Based Onion Quality Assessment & Deterministic Grading Backend (SIH 2026 PS26031)",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS Middleware (permitting Flutter mobile app & web dashboard access)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Structured Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start_time) * 1000, 2)
    logger.info(
        f"{request.method} {request.url.path} returned {response.status_code} in {duration_ms}ms"
    )
    return response


# Standardized Validation Error Handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    sanitized_errors = []
    for err in exc.errors():
        err_copy = dict(err)
        if "input" in err_copy and isinstance(err_copy["input"], (bytes, bytearray)):
            err_copy["input"] = f"<binary data: {len(err_copy['input'])} bytes>"
        sanitized_errors.append(err_copy)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error_code": "VALIDATION_ERROR",
            "message": "Invalid request parameters or payload",
            "details": sanitized_errors,
        },
    )


# Register Routers
app.include_router(health.router)
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(farmers.router, prefix=settings.API_V1_PREFIX)
app.include_router(procurement_centres.router, prefix=settings.API_V1_PREFIX)
app.include_router(lots.router, prefix=settings.API_V1_PREFIX)
app.include_router(inspections.router, prefix=settings.API_V1_PREFIX)
app.include_router(grading_policies.router, prefix=settings.API_V1_PREFIX)
app.include_router(model_versions.router, prefix=settings.API_V1_PREFIX)
app.include_router(reports.router, prefix=settings.API_V1_PREFIX)
app.include_router(audit_logs.router, prefix=settings.API_V1_PREFIX)
app.include_router(sync.router, prefix=settings.API_V1_PREFIX)

# Mount Web Dashboard
_web_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "web"))
if os.path.isdir(_web_dir):
    app.mount("/dashboard", StaticFiles(directory=_web_dir, html=True), name="dashboard")


@app.get("/")
def root_info():
    return {
        "project": "ONION_SURE",
        "competition": "Smart India Hackathon 2026",
        "problem_statement": "PS26031",
        "version": settings.APP_VERSION,
        "docs_url": "/docs",
        "dashboard_url": "/dashboard/",
        "health_check": "/health",
        "api_v1_prefix": settings.API_V1_PREFIX,
    }
