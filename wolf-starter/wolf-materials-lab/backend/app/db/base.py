"""Declarative base and model registration."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all persistence models."""


# Import models after Base exists so Alembic and metadata see every table.
from app.db import models as _models  # noqa: E402,F401
