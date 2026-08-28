"""Upload validation and storage-key safety.

The security boundary of the document vault, tested against the inputs an
attacker actually sends: a renamed executable, a traversal in the filename, a
declared content type that lies.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest

from app.storage.base import StorageError
from app.storage.local import LocalFileStorage
from app.utils.files import (
    ALLOWED_EXTENSIONS,
    FileValidationError,
    build_storage_key,
    inspect_upload,
    sanitise_filename,
)

# Real leading bytes. A test that invented its own would prove nothing about
# whether the signature check works on files a browser actually produces.
PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 32
#: The Windows executable header. The file this module exists to refuse.
EXE = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 32

ONE_MB = 1024 * 1024


class TestSanitiseFilename:
    def test_keeps_an_ordinary_name(self) -> None:
        assert sanitise_filename("passport.pdf") == "passport.pdf"

    @pytest.mark.parametrize(
        "raw",
        [
            "../../../etc/passwd.pdf",
            "..\\..\\windows\\system32\\config.pdf",
            "/etc/passwd.pdf",
            "C:\\Windows\\notepad.pdf",
        ],
    )
    def test_strips_every_directory_component(self, raw: str) -> None:
        """A multipart body treats the whole path as one 'filename'."""
        cleaned = sanitise_filename(raw)

        assert "/" not in cleaned
        assert "\\" not in cleaned
        assert ".." not in cleaned

    def test_collapses_repeated_dots(self) -> None:
        assert ".." not in sanitise_filename("a...b.pdf")

    def test_replaces_characters_that_do_not_belong_in_a_filename(self) -> None:
        cleaned = sanitise_filename("re;sum\u00e9 <script>.pdf")

        assert ";" not in cleaned
        assert "<" not in cleaned
        assert cleaned.endswith(".pdf")

    def test_transliterates_accents_so_the_name_is_portable(self) -> None:
        assert sanitise_filename("curr\u00edculum.pdf") == "curriculum.pdf"

    def test_truncates_a_very_long_name(self) -> None:
        assert len(sanitise_filename("a" * 500 + ".pdf")) <= 150

    def test_rejects_a_name_with_nothing_left(self) -> None:
        with pytest.raises(FileValidationError):
            sanitise_filename("///")


class TestInspectUpload:
    def test_accepts_a_real_pdf(self) -> None:
        result = inspect_upload(content=PDF, filename="offer.pdf", max_size_bytes=ONE_MB)

        assert result.content_type == "application/pdf"
        assert result.extension == ".pdf"
        assert result.size_bytes == len(PDF)

    @pytest.mark.parametrize(
        ("content", "filename", "expected"),
        [
            (PNG, "photo.png", "image/png"),
            (JPEG, "photo.jpg", "image/jpeg"),
            (JPEG, "photo.jpeg", "image/jpeg"),
        ],
    )
    def test_accepts_the_image_formats(self, content: bytes, filename: str, expected: str) -> None:
        assert (
            inspect_upload(content=content, filename=filename, max_size_bytes=ONE_MB).content_type == expected
        )

    def test_refuses_an_executable_renamed_to_pdf(self) -> None:
        """The attack this whole module exists for.

        The extension is allowed and the client would happily declare
        application/pdf; only the bytes give it away.
        """
        with pytest.raises(FileValidationError, match="does not look like"):
            inspect_upload(content=EXE, filename="invoice.pdf", max_size_bytes=ONE_MB)

    def test_refuses_a_disallowed_extension(self) -> None:
        with pytest.raises(FileValidationError, match="not accepted"):
            inspect_upload(content=PDF, filename="script.exe", max_size_bytes=ONE_MB)

    def test_refuses_svg_despite_it_being_an_image(self) -> None:
        """SVG is XML, it can carry script, and browsers execute it inline."""
        assert ".svg" not in ALLOWED_EXTENSIONS

        with pytest.raises(FileValidationError):
            inspect_upload(content=b"<svg/>", filename="logo.svg", max_size_bytes=ONE_MB)

    def test_refuses_content_that_disagrees_with_the_extension(self) -> None:
        with pytest.raises(FileValidationError, match="content is image/png"):
            inspect_upload(content=PNG, filename="scan.pdf", max_size_bytes=ONE_MB)

    def test_ignores_a_lying_declared_content_type(self) -> None:
        """The signature wins: browsers get this wrong for JPEGs routinely."""
        result = inspect_upload(
            content=PDF,
            filename="offer.pdf",
            max_size_bytes=ONE_MB,
            declared_content_type="application/octet-stream",
        )
        assert result.content_type == "application/pdf"

    def test_refuses_a_file_over_the_limit(self) -> None:
        oversized = PDF + b"\x00" * ONE_MB
        with pytest.raises(FileValidationError, match="larger than"):
            inspect_upload(content=oversized, filename="big.pdf", max_size_bytes=ONE_MB)

    def test_refuses_an_empty_file(self) -> None:
        with pytest.raises(FileValidationError, match="empty"):
            inspect_upload(content=b"", filename="empty.pdf", max_size_bytes=ONE_MB)

    def test_refuses_a_name_with_no_extension(self) -> None:
        with pytest.raises(FileValidationError):
            inspect_upload(content=PDF, filename="offer", max_size_bytes=ONE_MB)

    def test_reports_the_sanitised_name(self) -> None:
        """The traversal is gone before the name reaches the database."""
        result = inspect_upload(content=PDF, filename="../../secret.pdf", max_size_bytes=ONE_MB)
        assert ".." not in result.filename


class TestStorageKey:
    def test_never_contains_the_uploaded_filename(self) -> None:
        """The whole class of filename attacks disappears at the source."""
        key = build_storage_key(
            owner_type="employee",
            document_id=uuid.uuid4(),
            extension=".pdf",
            on=date(2026, 8, 4),
        )
        assert "secret" not in key
        assert key.endswith(".pdf")

    def test_is_unique_per_call(self) -> None:
        """Two versions must never land on the same key -- one would overwrite."""
        document_id = uuid.uuid4()
        keys = {
            build_storage_key(
                owner_type="employee", document_id=document_id, extension=".pdf", on=date(2026, 8, 4)
            )
            for _ in range(50)
        }
        assert len(keys) == 50

    def test_spreads_by_owner_type_and_month(self) -> None:
        key = build_storage_key(
            owner_type="candidate",
            document_id=uuid.uuid4(),
            extension=".png",
            on=date(2026, 8, 4),
        )
        assert key.startswith("candidate/2026/08/")


class TestLocalStorageSafety:
    @pytest.fixture
    def storage(self, tmp_path: Path) -> LocalFileStorage:
        return LocalFileStorage(tmp_path / "vault")

    async def test_saves_and_reads_back(self, storage: LocalFileStorage) -> None:
        stored = await storage.save(content=PDF, key="employee/2026/08/a.pdf")

        assert stored.size_bytes == len(PDF)
        assert await storage.read(stored.key) == PDF

    async def test_reports_a_checksum_that_identifies_the_content(self, storage: LocalFileStorage) -> None:
        first = await storage.save(content=PDF, key="a/1.pdf")
        second = await storage.save(content=PDF, key="a/2.pdf")

        assert first.checksum == second.checksum

    @pytest.mark.parametrize(
        "key",
        [
            "../escape.pdf",
            "employee/../../escape.pdf",
            "/etc/passwd",
            "\\windows\\system32",
            "C:/Windows/notepad.exe",
        ],
    )
    async def test_refuses_a_key_that_escapes_the_root(self, storage: LocalFileStorage, key: str) -> None:
        """Checked against the *resolved* path, so normalisation cannot hide it."""
        with pytest.raises(StorageError):
            await storage.save(content=PDF, key=key)

    async def test_never_writes_outside_the_root(self, storage: LocalFileStorage, tmp_path: Path) -> None:
        with pytest.raises(StorageError):
            await storage.save(content=PDF, key="../../outside.pdf")

        assert not (tmp_path / "outside.pdf").exists()
        assert not (tmp_path.parent / "outside.pdf").exists()

    async def test_refuses_to_overwrite(self, storage: LocalFileStorage) -> None:
        """Overwriting would destroy a version, so it is a bug rather than a race."""
        await storage.save(content=PDF, key="a/1.pdf")

        with pytest.raises(StorageError, match="already stored"):
            await storage.save(content=PNG, key="a/1.pdf")

    async def test_missing_key_is_distinguishable(self, storage: LocalFileStorage) -> None:
        from app.storage.base import StoredObjectNotFound

        with pytest.raises(StoredObjectNotFound):
            await storage.read("employee/2026/08/nothing.pdf")

    async def test_exists_is_false_rather_than_raising_for_a_bad_key(self, storage: LocalFileStorage) -> None:
        assert await storage.exists("../escape.pdf") is False

    async def test_leaves_no_partial_file_behind(self, storage: LocalFileStorage) -> None:
        """Written via a temporary file and renamed, so a crash cannot leave half."""
        await storage.save(content=PDF, key="a/1.pdf")

        leftovers = list(storage.root.rglob("*.part"))
        assert leftovers == []
