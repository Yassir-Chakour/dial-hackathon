"""FastAPI application factory and entry point."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    request_validation_exception_handler,
    unhandled_exception_handler,
)
from app.api.approvals import router as approvals_router
from app.api.corrections import router as corrections_router
from app.api.evidence import router as evidence_router
from app.api.health import router as health_router
from app.api.ingestion import router as ingestion_router
from app.api.recommendations import router as recommendations_router
from app.api.replays import router as replays_router
from app.api.review_queue import router as review_queue_router
from app.api.sources import router as sources_router
from app.api.workflows import router as workflows_router
from app.config import Settings, get_settings, get_settings_dependency
from app.logging import RequestCorrelationMiddleware, configure_logging


def build_app(settings: Settings | None = None, is_ready: bool = True) -> FastAPI:
    """Application factory: creates and configures a FastAPI instance.

    Tests can instantiate this factory with custom settings overrides without
    mutating global application state.
    """
    active_settings = settings or get_settings()

    # Configure structured logging for the current settings
    configure_logging(active_settings)

    # Disable interactive documentation in production
    is_production = active_settings.app_env == "production"
    docs_url = None if is_production else "/docs"
    redoc_url = None if is_production else "/redoc"
    openapi_url = None if is_production else "/openapi.json"

    app = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
        description=(
            "Wolf Materials Lab Backend API - Phase One Foundation.\n\n"
            "SYNTHETIC DATA NOTICE: All supplier datasets, invoices, and workflow "
            "scenarios in this environment are synthetic and simulated for hackathon "
            "evaluation. No client credentials, source databases, or real external "
            "systems are connected."
        ),
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )

    # Store settings and readiness state on application state
    app.state.settings = active_settings
    app.state.is_ready = is_ready

    # Async overrides avoid blocking the request threadpool in ASGI deployments.
    async def override_settings() -> Settings:
        return active_settings

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_settings_dependency] = override_settings

    # Correlation and access logging middleware
    app.add_middleware(RequestCorrelationMiddleware)

    # Restrict CORS to configured origins
    cors_origins = active_settings.cors_origins
    allow_credentials = "*" not in cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # Register standardized exception handlers
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(500, unhandled_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Mount versioned API routes
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(ingestion_router, prefix="/api/v1")
    app.include_router(sources_router, prefix="/api/v1")
    app.include_router(workflows_router, prefix="/api/v1")
    app.include_router(recommendations_router, prefix="/api/v1")
    app.include_router(evidence_router, prefix="/api/v1")
    app.include_router(corrections_router, prefix="/api/v1")
    app.include_router(approvals_router, prefix="/api/v1")
    app.include_router(replays_router, prefix="/api/v1")
    app.include_router(review_queue_router, prefix="/api/v1")

    return app


# Default ASGI application instance for uvicorn
app = build_app()
