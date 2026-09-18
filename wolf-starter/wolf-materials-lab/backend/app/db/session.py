"""SQLAlchemy engine, session factory and transaction helpers."""

from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings


class Database:
    """A database handle with an explicit session/transaction boundary."""

    def __init__(self, settings: Settings) -> None:
        connect_args: dict[str, object] = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            if settings.database_url.startswith("sqlite:///"):
                Path(settings.database_url.removeprefix("sqlite:///" )).parent.mkdir(
                    parents=True, exist_ok=True
                )
        self.engine = create_engine(
            settings.database_url,
            echo=settings.database_echo,
            connect_args=connect_args,
            future=True,
        )
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, class_=Session)
        if settings.database_url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def _configure_sqlite(dbapi_connection: object, _connection_record: object) -> None:
                cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute(f"PRAGMA busy_timeout={settings.database_busy_timeout_ms}")
                cursor.close()

    def create_schema(self) -> None:
        from app.db.base import Base

        Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()

    @contextmanager
    def transaction(self) -> Generator[Session, None, None]:
        with self.session_factory.begin() as session:
            yield session

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        with self.session_factory() as session:
            yield session


def create_database(settings: Settings) -> Database:
    return Database(settings)


_databases: dict[str, Database] = {}


def get_database(settings: Settings | None = None) -> Database:
    """Retrieve or create cached database instance for settings."""
    from app.config import get_settings

    active_settings = settings or get_settings()
    url = active_settings.database_url
    if url not in _databases:
        _databases[url] = create_database(active_settings)
    return _databases[url]


async def get_db() -> AsyncGenerator[Session, None]:
    """FastAPI dependency that yields an active database session."""
    db = get_database()
    with db.session() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
