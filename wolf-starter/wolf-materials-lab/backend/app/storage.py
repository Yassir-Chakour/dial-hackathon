"""Private source-object storage primitives.

The production implementation can be backed by S3-compatible storage; the
local implementation intentionally has the same opaque-key and retention
semantics so development does not silently rely on public filenames or URLs.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class StorageError(Exception):
    """Base error for private object-storage operations."""


class RetentionError(StorageError):
    """Raised when an object is protected by retention or legal hold."""


@dataclass(frozen=True)
class StoredObject:
    object_key: str
    sha256: str
    size_bytes: int
    media_type: str
    created_at: datetime


class PrivateObjectStore:
    """Filesystem-backed private object store with opaque server-generated keys."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, object_key: str) -> Path:
        candidate = (self.root / object_key).resolve()
        if self.root not in candidate.parents:
            raise StorageError("Object key escapes the private storage root.")
        return candidate

    def put(self, content: bytes, *, media_type: str) -> StoredObject:
        digest = hashlib.sha256(content).hexdigest()
        object_key = f"objects/{digest[:2]}/{uuid4().hex}"
        destination = self._path(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, destination)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        return StoredObject(object_key, digest, len(content), media_type, datetime.now(timezone.utc))

    def get(self, object_key: str) -> bytes:
        path = self._path(object_key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageError("Object does not exist.") from exc

    def delete(self, object_key: str, *, retention_status: str = "active") -> None:
        if retention_status in {"legal_hold", "retained"}:
            raise RetentionError("Object is protected by retention policy.")
        try:
            self._path(object_key).unlink()
        except FileNotFoundError:
            return

