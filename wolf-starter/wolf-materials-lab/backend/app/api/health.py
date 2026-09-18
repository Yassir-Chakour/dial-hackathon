"""Health probe endpoints: liveness and readiness."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from starlette.responses import JSONResponse, Response

from app.config import Settings, get_settings_dependency
from app.schemas.common import ServiceStatus

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=ServiceStatus, status_code=status.HTTP_200_OK)
async def liveness(
    settings: Annotated[Settings, Depends(get_settings_dependency)],
) -> ServiceStatus:
    """Liveness probe: answers whether the process is running.

    Must never call external networks, databases, filesystems, or model providers.
    """
    return ServiceStatus(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )


@router.get("/ready", response_model=ServiceStatus, status_code=status.HTTP_200_OK)
async def readiness(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_dependency)],
) -> Response:
    """Readiness probe: answers whether the application is configured to accept work.

    In Phase One, verifies application startup configuration.
    Returns HTTP 200 when ready, HTTP 503 when not ready.
    """
    # Verify readiness state on app
    is_ready = bool(getattr(request.app.state, "is_ready", True))

    checks: dict[str, str] = {
        "configuration": "ok" if is_ready else "failed",
    }

    if not is_ready:
        payload = ServiceStatus(
            status="not_ready",
            service=settings.app_name,
            version=settings.app_version,
            checks=checks,  # type: ignore[arg-type]
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServiceStatus(
            status="ready",
            service=settings.app_name,
            version=settings.app_version,
            checks=checks,  # type: ignore[arg-type]
        ).model_dump(),
    )
