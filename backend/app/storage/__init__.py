"""Document storage.

Infrastructure, alongside :mod:`app.db` -- not business logic. The document
service depends on the :class:`StorageBackend` protocol and never on a concrete
backend, which is what lets object storage replace local disk later without any
service change.

Adding S3 is: write ``app/storage/s3.py`` implementing the protocol, add the
setting that selects it, and extend :func:`get_storage`. Nothing above this
package moves.
"""

from functools import lru_cache

from app.core.config import settings
from app.storage.base import (
    StorageBackend,
    StorageError,
    StoredFile,
    StoredObjectNotFound,
)
from app.storage.local import LocalFileStorage


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    """The process-wide storage backend.

    Cached because constructing one resolves and creates the root directory,
    and every request would otherwise repeat that syscall.
    """
    return LocalFileStorage(settings.UPLOAD_DIR)


__all__ = [
    "LocalFileStorage",
    "StorageBackend",
    "StorageError",
    "StoredFile",
    "StoredObjectNotFound",
    "get_storage",
]
