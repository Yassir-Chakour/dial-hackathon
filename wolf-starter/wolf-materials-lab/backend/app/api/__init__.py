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
from app.api.health import router as health_router
from app.api.ingestion import router as ingestion_router

__all__ = [
    "AppException",
    "ConflictError",
    "DependencyUnavailableError",
    "InvalidRequestError",
    "NotFoundError",
    "NotReadyError",
    "app_exception_handler",
    "health_router",
    "http_exception_handler",
    "ingestion_router",
    "request_validation_exception_handler",
    "safe_error_response",
    "unhandled_exception_handler",
]

