"""API routers and error handlers for Wolf Materials Lab backend."""

from app.api.errors import (
    AppException,
    ConflictError,
    DependencyUnavailableError,
    InvalidRequestError,
    NotFoundError,
    NotReadyError,
    app_exception_handler,
    http_exception_handler,
    request_validation_exception_handler,
    safe_error_response,
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

__all__ = [
    "AppException",
    "ConflictError",
    "DependencyUnavailableError",
    "InvalidRequestError",
    "NotFoundError",
    "NotReadyError",
    "app_exception_handler",
    "approvals_router",
    "corrections_router",
    "evidence_router",
    "health_router",
    "http_exception_handler",
    "ingestion_router",
    "recommendations_router",
    "replays_router",
    "request_validation_exception_handler",
    "review_queue_router",
    "safe_error_response",
    "sources_router",
    "unhandled_exception_handler",
    "workflows_router",
]


