"""Upload validation and filename handling.

The security boundary for the document vault. Everything here treats the client
as untrusted: the filename, the declared content type and the extension are all
attacker-controlled, and only the *bytes* are evidence of what a file actually
is.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import date

#: The only file kinds the vault accepts.
#:
#: Deliberately a constant rather than a setting. The size limit and the storage
#: path are operator preferences; this is a security control, and an environment
#: variable that can be edited to include ``.exe`` or ``.svg`` is a control that
#: can be turned off by whoever gets there first. Widening it should be a code
#: change that a reviewer sees.
#:
#: SVG is excluded despite being an image: it is XML, it can carry script, and
#: browsers execute it when it is served inline.
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".jpg", ".jpeg", ".png"})

#: Leading bytes that prove what a file really is, mapped to the extensions that
#: may legitimately carry them.
_SIGNATURES: tuple[tuple[bytes, str, frozenset[str]], ...] = (
    (b"%PDF-", "application/pdf", frozenset({".pdf"})),
    (b"\xff\xd8\xff", "image/jpeg", frozenset({".jpg", ".jpeg"})),
    (b"\x89PNG\r\n\x1a\n", "image/png", frozenset({".png"})),
)

#: Enough bytes to cover the longest signature above, with room to spare.
SIGNATURE_PROBE_BYTES = 16

_UNSAFE_CHARACTERS = re.compile(r"[^A-Za-z0-9._-]+")
_REPEATED_DOTS = re.compile(r"\.{2,}")

#: Longest filename kept for display. Well under any filesystem limit, and the
#: stored name is a generated UUID regardless.
MAX_FILENAME_LENGTH = 150


class FileValidationError(ValueError):
    """The upload is not something the vault will accept."""


@dataclass(frozen=True)
class InspectedFile:
    """The result of looking at an upload's actual bytes."""

    #: Sanitised, display-safe original name.
    filename: str
    extension: str
    #: Derived from the content signature, not from what the client declared.
    content_type: str
    size_bytes: int


def sanitise_filename(raw: str) -> str:
    """Reduce a client-supplied filename to something safe to store and show.

    Strips any directory component first: browsers normally send a bare name,
    but ``../../../etc/passwd`` is a single "filename" as far as a multipart
    body is concerned.
    """
    # Both separators, because a Windows client posting to a Linux server sends
    # backslashes that os.path would not treat as a separator.
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]

    # Strip accents to ASCII so the stored name is portable across filesystems.
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")

    name = _UNSAFE_CHARACTERS.sub("_", name)
    # "..." collapses to "." so no sequence of dots can survive as a traversal.
    name = _REPEATED_DOTS.sub(".", name).strip("._-")

    if not name:
        raise FileValidationError("The file needs a name.")

    return name[:MAX_FILENAME_LENGTH]


def split_extension(filename: str) -> tuple[str, str]:
    """Return the stem and the lower-cased extension, including the dot."""
    stem, _, suffix = filename.rpartition(".")
    if not stem:
        raise FileValidationError("The file needs an extension, for example .pdf.")
    return stem, f".{suffix.lower()}"


def inspect_upload(
    *,
    content: bytes,
    filename: str,
    max_size_bytes: int,
    declared_content_type: str | None = None,
) -> InspectedFile:
    """Validate an upload and report what it actually is.

    Order matters. Size is checked first because it is cheapest; the signature
    is checked last and is what the result reports, because the client's
    declared content type and the extension are both claims rather than
    evidence.
    """
    if not content:
        raise FileValidationError("The file is empty.")

    if len(content) > max_size_bytes:
        limit_mb = max_size_bytes / (1024 * 1024)
        raise FileValidationError(f"The file is larger than the {limit_mb:.0f} MB limit.")

    safe_name = sanitise_filename(filename)
    _, extension = split_extension(safe_name)

    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise FileValidationError(f"{extension} files are not accepted. Allowed types: {allowed}.")

    head = content[:SIGNATURE_PROBE_BYTES]
    for signature, content_type, extensions in _SIGNATURES:
        if not head.startswith(signature):
            continue

        if extension not in extensions:
            # A PNG named .pdf. Usually a mistake, occasionally an attempt to
            # get a file served with a content type it does not deserve.
            raise FileValidationError(
                f"The file content is {content_type} but the name ends in {extension}. "
                "Rename it to match, or upload the right file."
            )

        if declared_content_type and declared_content_type.split(";")[0].strip() != content_type:
            # Not fatal -- browsers get this wrong for JPEGs routinely -- so the
            # signature wins and the claim is ignored.
            pass

        return InspectedFile(
            filename=safe_name,
            extension=extension,
            content_type=content_type,
            size_bytes=len(content),
        )

    # Extension allowed, content unrecognised: a renamed executable, an archive,
    # or a corrupt file. All three are refused.
    raise FileValidationError(
        "The file does not look like a PDF, JPEG or PNG. Check that it is not corrupt "
        "and that it has not been renamed from another format."
    )


def build_storage_key(*, owner_type: str, document_id: uuid.UUID, extension: str, on: date) -> str:
    """Compose the opaque key a version's content is stored under.

    Three properties matter:

    * **Unique.** A fresh UUID per version, so a new version can never land on
      an existing one and destroy it.
    * **Free of user input.** The original filename is kept in the database for
      display and never reaches the filesystem, which removes the whole class of
      filename-based attacks at the source.
    * **Spread out.** Owner type, then year and month, so no single directory
      accumulates every document ever uploaded.
    """
    return f"{owner_type}/{on:%Y/%m}/{document_id}/{uuid.uuid4().hex}{extension}"
