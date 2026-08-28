"""Storage backend contract.

The document service knows only this interface. Swapping local disk for S3,
Azure Blob or MinIO is implementing :class:`StorageBackend` and changing one
line in :func:`app.storage.get_storage` -- no business logic moves.

Two rules make that possible:

* **The service never sees a filesystem path.** It hands over bytes and gets
  back a *key*: an opaque, backend-defined string it stores and hands back later
  to read or delete. On disk a key happens to be a relative path; on S3 it is an
  object key. Neither is a URL and neither is ever returned by the API.
* **Reads return bytes, not handles.** A file handle is a local-disk concept.
  Returning bytes keeps the contract honest about what a remote backend can
  offer, and these are documents rather than video.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class StorageError(RuntimeError):
    """A storage operation failed for a reason the caller cannot fix."""


class StoredObjectNotFound(StorageError):
    """The key does not resolve to anything.

    Distinct from a generic failure because it means the database and the
    storage backend disagree -- a row exists whose file does not -- which is an
    operational problem rather than a transient one.
    """


@dataclass(frozen=True)
class StoredFile:
    """What a backend returns after accepting content."""

    #: Opaque handle the caller stores and passes back. Never shown to a user.
    key: str
    #: Bytes actually written, for reconciling against what was declared.
    size_bytes: int
    #: SHA-256 of the content, used to recognise a re-upload of the same file.
    checksum: str


@runtime_checkable
class StorageBackend(Protocol):
    """Where document content lives."""

    async def save(self, *, content: bytes, key: str) -> StoredFile:
        """Write ``content`` at ``key``, creating any container it needs.

        Must not silently overwrite: the document service generates a unique key
        per version, so a collision means a bug, and hiding it would destroy the
        previous version.
        """
        ...

    async def read(self, key: str) -> bytes:
        """Return the content at ``key``, or raise :class:`StoredObjectNotFound`."""
        ...

    async def delete(self, key: str) -> None:
        """Remove the object at ``key``.

        Reserved for a retention job. Nothing in the application calls this --
        documents are archived, never deleted.
        """
        ...

    async def exists(self, key: str) -> bool:
        """Whether anything is stored at ``key``."""
        ...
