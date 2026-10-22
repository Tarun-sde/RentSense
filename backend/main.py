import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.api.v1.router import api_v1_router
from app.services.telemetry_simulator import telemetry_simulator

# Configure Structured Logging
log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("rentsense")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION} [{settings.ENVIRONMENT.upper()}]")
    logger.info(f"CORS Allowed Origins: {settings.cors_origin_list}")
    await telemetry_simulator.start()
    try:
        yield
    finally:
        await telemetry_simulator.stop()
        logger.info(f"Shutting down {settings.PROJECT_NAME}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Smart rental tracking, fleet intelligence, and automated ROI analytics for heavy equipment",
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Configuration
allow_origins = settings.cors_origin_list if settings.cors_origin_list else ["http://localhost:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)


# Global Exception Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error on {request.method} {request.url.path}")
    sanitized_errors = jsonable_encoder(exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": "Invalid request payload or query parameters.",
            "detail": sanitized_errors,
            "details": sanitized_errors,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.info(f"HTTP {exc.status_code} on {request.method} {request.url.path}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "error_code": f"HTTP_{exc.status_code}",
            "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            "detail": exc.detail,
        },
    )


@app.exception_handler(Exception)
async def global_unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected operational error occurred. Please contact the fleet administrator.",
            "detail": "Internal Server Error",
        },
    )


# Health & Readiness Endpoints
@app.get("/health", tags=["System"])
def health_check():
    """Liveness probe confirming the web process is running."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/ready", tags=["System"])
def readiness_check():
    """Readiness probe confirming database connectivity."""
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "connected",
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "database": "disconnected",
                "message": "Database connection unavailable.",
                "detail": "Database connection unavailable.",
            },
        )
    finally:
        db.close()


# Mount API Routes
app.include_router(api_v1_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
