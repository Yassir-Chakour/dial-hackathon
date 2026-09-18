"""Unified error handling, custom exceptions, and error response envelopes."""

import logging

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.logging import get_request_id
from app.schemas.common import ErrorDetail, ErrorResponse

logger = logging.getLogger("app.errors")


class AppException(Exception):
    """Base application exception for domain errors."""

    def __init__(
        self,
        message: str = "An internal error occurred.",
        code: str = "internal_error",
        status_code: int = 500,
        details: list[ErrorDetail] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or []


class NotFoundError(AppException):
    """Resource not found error."""

    def __init__(self, message: str = "The requested resource was not found.") -> None:
        super().__init__(message=message, code="not_found", status_code=404)


class InvalidRequestError(AppException):
    """Invalid client request error."""

    def __init__(
        self,
        message: str = "The request was invalid or malformed.",
        details: list[ErrorDetail] | None = None,
    ) -> None:
        super().__init__(
            message=message, code="invalid_request", status_code=400, details=details
        )


class NotReadyError(AppException):
    """Service not ready error."""

    def __init__(self, message: str = "Service is not ready to accept requests.") -> None:
        super().__init__(message=message, code="not_ready", status_code=503)


class ConflictError(AppException):
    """Resource conflict error."""

    def __init__(self, message: str = "A conflict occurred with existing resource state.") -> None:
        super().__init__(message=message, code="conflict", status_code=409)


class DependencyUnavailableError(AppException):
    """External dependency unavailable error."""

    def __init__(self, message: str = "An external dependency is currently unavailable.") -> None:
        super().__init__(message=message, code="dependency_unavailable", status_code=503)


def _get_context_request_id(request: Request) -> str:
    """Retrieve existing request ID from state or extract/generate one."""
    req_id = getattr(request.state, "request_id", None)
    if isinstance(req_id, str) and req_id:
        return req_id
    return get_request_id(request)


def safe_error_response(
    code: str,
    message: str,
    request_id: str,
    status_code: int = 500,
    details: list[ErrorDetail] | None = None,
) -> JSONResponse:
    """Construct a standardized ErrorResponse JSONResponse."""
    payload = ErrorResponse(
        code=code,
        message=message,
        request_id=request_id,
        details=details or [],
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(),
        headers={
            "X-Request-ID": request_id,
            "X-Content-Type-Options": "nosniff",
        },
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handler for application-level domain exceptions."""
    request_id = _get_context_request_id(request)
    return safe_error_response(
        code=exc.code,
        message=exc.message,
        request_id=request_id,
        status_code=exc.status_code,
        details=exc.details,
    )


async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handler for Pydantic and FastAPI validation errors."""
    request_id = _get_context_request_id(request)
    details: list[ErrorDetail] = []
    for err in exc.errors():
        raw_loc = err.get("loc", ())
        loc: list[str | int] = [
            x if isinstance(x, (str, int)) else str(x) for x in raw_loc
        ]
        msg = str(err.get("msg", "Validation error"))
        err_type = str(err.get("type", "value_error"))
        details.append(ErrorDetail(loc=loc, msg=msg, type=err_type))

    return safe_error_response(
        code="invalid_request",
        message="Request validation failed.",
        request_id=request_id,
        status_code=422,
        details=details,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handler for Starlette/FastAPI HTTP exceptions."""
    request_id = _get_context_request_id(request)
    status_code = exc.status_code

    code_map: dict[int, str] = {
        400: "invalid_request",
        404: "not_found",
        409: "conflict",
        503: "dependency_unavailable",
    }
    code = code_map.get(status_code, "internal_error" if status_code >= 500 else "invalid_request")

    # Safe message defaults
    message = str(exc.detail) if exc.detail else "An HTTP error occurred."
    if status_code == 404 and (not exc.detail or exc.detail == "Not Found"):
        message = "The requested resource was not found."

    return safe_error_response(
        code=code,
        message=message,
        request_id=request_id,
        status_code=status_code,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handler for unexpected unhandled exceptions (500). Never leak tracebacks or secrets."""
    request_id = _get_context_request_id(request)
    logger.exception(
        "Unhandled exception processing request",
        extra={"request_id": request_id, "path": request.url.path},
    )
    return safe_error_response(
        code="internal_error",
        message="An unexpected error occurred. Please contact support with the request ID.",
        request_id=request_id,
        status_code=500,
    )
