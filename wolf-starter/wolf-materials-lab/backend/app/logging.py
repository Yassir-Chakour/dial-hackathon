"""Structured logging configuration, redaction, and request correlation middleware."""

import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import Settings

REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")
SENSITIVE_KEYS = {
    "authorization",
    "token",
    "password",
    "secret",
    "content",
    "prompt",
    "source_data",
    "cookie",
    "api_key",
}

logger = logging.getLogger("app.access")


def redact_mapping(value: Any) -> Any:
    """Recursively redact sensitive keys from mappings and lists."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for k, v in value.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in SENSITIVE_KEYS):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_mapping(v)
        return redacted
    if isinstance(value, (list, tuple, set)):
        return [redact_mapping(item) for item in value]
    return value


def get_request_id(request: Request) -> str:
    """Validate and return request ID from header, or generate a fresh UUID4."""
    header_val = request.headers.get("X-Request-ID")
    if header_val and REQUEST_ID_REGEX.match(header_val.strip()):
        return header_val.strip()
    return str(uuid.uuid4())


class JsonLogFormatter(logging.Formatter):
    """Format log records as structured JSON without secrets or source data."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for attr in ("request_id", "method", "path", "status_code", "duration_ms"):
            val = getattr(record, attr, None)
            if val is not None:
                log_obj[attr] = val

        # Ensure no accidental sensitive keys leaked
        safe_obj = redact_mapping(log_obj)
        return json.dumps(safe_obj)


def configure_logging(settings: Settings) -> None:
    """Configure structured logging for the application."""
    root_logger = logging.getLogger()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers on re-configuration
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setLevel(log_level)
    handler.setFormatter(JsonLogFormatter())
    root_logger.addHandler(handler)


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Middleware for request correlation, duration measurement, and security headers."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        request_id = get_request_id(request)
        request.state.request_id = request_id
        start_time = time.perf_counter()

        response: Response
        try:
            response = await call_next(request)
        except Exception as exc:
            # Safely handle unhandled exception using the public error envelope
            from app.api.errors import unhandled_exception_handler

            response = await unhandled_exception_handler(request, exc)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Log request completion (omit bodies/query secrets)
        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
