"""Local filesystem storage backend.

The default backend, and the one that has to be most careful: a key is turned
into a real path, so a malicious key is a directory-traversal attempt. Every
path is resolved and checked against the configured root before anything is
opened.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path

from app.core.logging import get_logger
from app.storage.base import StorageError, StoredFile, StoredObjectNotFound

logger = get_logger("storage.local")


class LocalFileStorage:
    """Stores document content under a configured root directory."""

    def __init__(self, root: str | Path) -> None:
        # Resolved once, at construction. Every later comparison is against this
        # absolute, symlink-free path.
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------
    # Path safety
    # ------------------------------------------------------------------
    def _resolve(self, key: str) -> Path:
        """Turn a storage key into an absolute path inside the root.

        This is the module's single security-critical function. ``key`` reaches
        it from the database, and a row written before a validation rule existed
        -- or by a future import -- must not be able to read ``/etc/passwd`` or
        write outside the vault.

        Checking the *resolved* path rather than the raw string is what makes it
        sound: ``a/../../b`` and a symlinked directory both normalise away
        before the comparison.
        """
        if not key or key.startswith(("/", "\\")) or ":" in key:
            raise StorageError("Invalid storage key.")

        candidate = (self._root / key).resolve()

        if candidate != self._root and self._root not in candidate.parents:
            # Deliberately vague to the caller, specific in the log: the person
            # triggering this does not need confirmation of what they attempted.
            logger.error("Rejected a storage key resolving outside the root", extra={"key": key})
            raise StorageError("Invalid storage key.")

        return candidate

    # ------------------------------------------------------------------
    # Operations
    #
    # Each runs the blocking filesystem call in a worker thread. Reading a
    # multi-megabyte PDF on the event loop would stall every other request in
    # the process for the duration.
    # ------------------------------------------------------------------
    async def save(self, *, content: bytes, key: str) -> StoredFile:
        path = self._resolve(key)
        if path.exists():
            # The service generates a unique key per version, so this is a bug
            # rather than a race -- and overwriting would destroy a version.
            raise StorageError("Something is already stored under that key.")

        await asyncio.to_thread(self._write_atomic, path, content)

        return StoredFile(
            key=key,
            size_bytes=len(content),
            checksum=hashlib.sha256(content).hexdigest(),
        )

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        """Write via a temporary file in the same directory, then rename.

        A rename within one filesystem is atomic, so a crash mid-write leaves
        either nothing or the complete file -- never a half-written document
        that looks valid to the database.
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".part")
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    async def read(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.is_file():
            raise StoredObjectNotFound(f"No stored object for key {key!r}.")
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        await asyncio.to_thread(path.unlink, True)

    async def exists(self, key: str) -> bool:
        try:
            return await asyncio.to_thread(self._resolve(key).is_file)
        except StorageError:
            return False
