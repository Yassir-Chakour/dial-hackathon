from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.errors import ConflictError, DependencyUnavailableError
from app.config import Settings
from app.db.session import create_database, get_db
from app.main import build_app



class ExampleValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=2, max_length=50)
    count: int = Field(..., ge=1, le=100)


def create_test_router() -> APIRouter:
    """Create test routes to probe validation, domain errors, and unhandled exceptions."""
    test_router = APIRouter(prefix="/api/v1/test", tags=["test"])

    @test_router.post("/validate")
    async def probe_validation(body: ExampleValidationRequest) -> dict[str, str]:
        return {"received": body.name}

    @test_router.get("/unhandled-error")
    async def probe_unhandled() -> dict[str, str]:
        raise RuntimeError("simulated secret internal error: database_url=postgresql://admin:secret123@db")

    @test_router.get("/conflict-error")
    async def probe_conflict() -> dict[str, str]:
        raise ConflictError("A version conflict occurred for France source file.")

    @test_router.get("/dependency-error")
    async def probe_dependency() -> dict[str, str]:
        raise DependencyUnavailableError("Model provider is unreachable.")

    return test_router


@pytest.fixture
def test_settings() -> Settings:
    """Provide isolated test settings."""
    return Settings(
        app_env="test",
        app_name="wolf-materials-backend-test",
        app_version="0.1.0-test",
        log_level="DEBUG",
        cors_origins=["http://127.0.0.1:8084"],
        api_host="127.0.0.1",
        api_port=8000,
        model_token="super-secret-token",  # type: ignore[arg-type]
    )


@pytest.fixture
def app(test_settings: Settings, tmp_path: Path):

    """Create FastAPI application with test settings, isolated SQLite DB, and probe routes."""
    db_path = tmp_path / "test_api.db"
    settings = test_settings.model_copy(update={"database_url": f"sqlite:///{db_path}"})
    db = create_database(settings)
    db.create_schema()

    application = build_app(settings=settings)
    application.include_router(create_test_router())

    async def override_get_db() -> AsyncGenerator[Session, None]:
        with db.session() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    application.dependency_overrides[get_db] = override_get_db
    application.state.test_db = db
    return application



@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for testing endpoints."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as ac:
        yield ac
