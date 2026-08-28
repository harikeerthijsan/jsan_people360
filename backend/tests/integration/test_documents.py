"""Document vault API.

Exercises the real HTTP stack, the real database and a real storage root
redirected to a temporary directory. The emphasis is on what would be expensive
to get wrong: that uploading never overwrites, that a renamed executable is
refused, that no response leaks a storage path, and that reads are recorded.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.business_unit import BusinessUnit
from app.models.designation import Designation
from app.models.document_category import DocumentCategory, DocumentType
from app.models.employee import Employee
from app.models.employment_type import EmploymentType
from app.models.enums import RecordStatus
from app.models.grade import Grade
from app.models.location import Location
from app.models.recruitment import Candidate, CandidateSource, JobOpening, RecruitmentStage
from app.models.requisition import JobRequisition
from app.models.user import User
from app.storage import get_storage

pytestmark = pytest.mark.asyncio

BASE = f"{settings.API_V1_PREFIX}/documents"

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 32
EXE = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 32


@pytest.fixture(autouse=True)
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the vault at a temporary directory for the duration of a test.

    ``get_storage`` is cached, so the cache is cleared on the way in and out --
    otherwise the first test would fix the root for the whole session and later
    tests would write into each other's directories.
    """
    root = tmp_path / "vault"
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(root))
    get_storage.cache_clear()
    yield root
    get_storage.cache_clear()


@pytest.fixture
async def category(db_session: AsyncSession) -> DocumentCategory:
    record = DocumentCategory(
        name="Identity Documents", code=f"ID{uuid.uuid4().hex[:6].upper()}", status=RecordStatus.ACTIVE
    )
    db_session.add(record)
    await db_session.flush()
    return record


@pytest.fixture
async def document_type(db_session: AsyncSession, category: DocumentCategory) -> DocumentType:
    record = DocumentType(
        name="Passport",
        code=f"PP{uuid.uuid4().hex[:6].upper()}",
        category_id=category.id,
        status=RecordStatus.ACTIVE,
    )
    db_session.add(record)
    await db_session.flush()
    return record


def upload_form(
    *, category: DocumentCategory, document_type: DocumentType, owner: Employee, **overrides: Any
) -> dict[str, Any]:
    return {
        "name": "Passport",
        "category_id": str(category.id),
        "document_type_id": str(document_type.id),
        "owner_type": "employee",
        "owner_id": str(owner.id),
        **overrides,
    }


async def upload(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    category: DocumentCategory,
    document_type: DocumentType,
    owner: Employee,
    content: bytes = PDF,
    filename: str = "passport.pdf",
    **overrides: Any,
) -> dict[str, Any]:
    response = await client.post(
        BASE,
        data=upload_form(category=category, document_type=document_type, owner=owner, **overrides),
        files={"file": (filename, content, "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


# ----------------------------------------------------------------------
class TestAuthentication:
    async def test_every_route_needs_a_token(self, client: AsyncClient) -> None:
        assert (await client.get(BASE)).status_code == 401
        assert (await client.get(f"{BASE}/dashboard")).status_code == 401


# ----------------------------------------------------------------------
class TestUpload:
    async def test_uploads_a_document(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        data = await upload(
            client, auth_headers, category=category, document_type=document_type, owner=employee
        )

        assert data["document_code"].startswith("DOC-")
        assert data["status"] == "uploaded"
        assert data["version_count"] == 1
        assert data["current_version"]["version_number"] == 1
        assert data["current_version"]["content_type"] == "application/pdf"

    async def test_generates_a_sequential_document_code(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        first = await upload(
            client, auth_headers, category=category, document_type=document_type, owner=employee
        )
        second = await upload(
            client,
            auth_headers,
            category=category,
            document_type=document_type,
            owner=employee,
            content=PNG,
            filename="passport.png",
        )

        assert int(second["document_code"][4:]) == int(first["document_code"][4:]) + 1

    async def test_writes_the_file_to_storage(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
        storage_root: Path,
    ) -> None:
        await upload(client, auth_headers, category=category, document_type=document_type, owner=employee)

        stored = list(storage_root.rglob("*.pdf"))
        assert len(stored) == 1
        assert stored[0].read_bytes() == PDF

    async def test_the_stored_filename_is_not_the_uploaded_one(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
        storage_root: Path,
    ) -> None:
        """User input never reaches the filesystem."""
        await upload(
            client,
            auth_headers,
            category=category,
            document_type=document_type,
            owner=employee,
            filename="my secret passport.pdf",
        )

        stored = next(iter(storage_root.rglob("*.pdf")))
        assert "secret" not in stored.name

    async def test_resolves_the_owner_to_a_name(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        """A bare type and UUID would be unusable in a list."""
        data = await upload(
            client, auth_headers, category=category, document_type=document_type, owner=employee
        )

        assert data["owner"]["display_name"] == employee.full_name
        assert data["owner"]["reference_code"] == employee.employee_code

    async def test_refuses_an_executable_renamed_to_pdf(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
        storage_root: Path,
    ) -> None:
        response = await client.post(
            BASE,
            data=upload_form(category=category, document_type=document_type, owner=employee),
            files={"file": ("invoice.pdf", EXE, "application/pdf")},
            headers=auth_headers,
        )

        assert response.status_code == 422
        assert response.json()["errors"][0]["code"] == "invalid_file"
        # Nothing was written before the check ran.
        assert list(storage_root.rglob("*")) == [] or not any(p.is_file() for p in storage_root.rglob("*"))

    async def test_refuses_a_disallowed_extension(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        response = await client.post(
            BASE,
            data=upload_form(category=category, document_type=document_type, owner=employee),
            files={"file": ("payload.exe", EXE, "application/octet-stream")},
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_refuses_a_traversal_in_the_filename(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
        storage_root: Path,
    ) -> None:
        """Accepted, but the traversal is stripped rather than honoured."""
        response = await client.post(
            BASE,
            data=upload_form(category=category, document_type=document_type, owner=employee),
            files={"file": ("../../../etc/passwd.pdf", PDF, "application/pdf")},
            headers=auth_headers,
        )

        assert response.status_code == 201
        assert ".." not in response.json()["data"]["current_version"]["original_filename"]
        assert all(storage_root in path.parents for path in storage_root.rglob("*") if path.is_file())

    async def test_refuses_an_unknown_owner(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        response = await client.post(
            BASE,
            data=upload_form(
                category=category,
                document_type=document_type,
                owner=employee,
                owner_id=str(uuid.uuid4()),
            ),
            files={"file": ("passport.pdf", PDF, "application/pdf")},
            headers=auth_headers,
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "invalid_owner"

    async def test_refuses_a_type_from_another_category(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        """Both ids are valid, so only the service can catch the mismatch."""
        other = DocumentCategory(
            name="Contracts", code=f"CT{uuid.uuid4().hex[:6].upper()}", status=RecordStatus.ACTIVE
        )
        db_session.add(other)
        await db_session.flush()

        response = await client.post(
            BASE,
            data=upload_form(
                category=category,
                document_type=document_type,
                owner=employee,
                category_id=str(other.id),
            ),
            files={"file": ("passport.pdf", PDF, "application/pdf")},
            headers=auth_headers,
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "category_mismatch"

    async def test_requires_an_expiry_when_the_type_says_so(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        category: DocumentCategory,
        employee: Employee,
    ) -> None:
        expiring = DocumentType(
            name="Visa",
            code=f"VS{uuid.uuid4().hex[:6].upper()}",
            category_id=category.id,
            requires_expiry=True,
            status=RecordStatus.ACTIVE,
        )
        db_session.add(expiring)
        await db_session.flush()

        response = await client.post(
            BASE,
            data=upload_form(category=category, document_type=expiring, owner=employee),
            files={"file": ("visa.pdf", PDF, "application/pdf")},
            headers=auth_headers,
        )

        assert response.status_code == 422
        assert response.json()["errors"][0]["code"] == "expiry_required"

    async def test_honours_a_types_own_narrowing(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        category: DocumentCategory,
        employee: Employee,
    ) -> None:
        """A signed contract is PDF only: a photograph of one is not a contract."""
        pdf_only = DocumentType(
            name="NDA",
            code=f"ND{uuid.uuid4().hex[:6].upper()}",
            category_id=category.id,
            allowed_extensions=".pdf",
            status=RecordStatus.ACTIVE,
        )
        db_session.add(pdf_only)
        await db_session.flush()

        response = await client.post(
            BASE,
            data=upload_form(category=category, document_type=pdf_only, owner=employee),
            files={"file": ("nda.png", PNG, "image/png")},
            headers=auth_headers,
        )

        assert response.status_code == 422
        assert "only .pdf" in response.json()["message"]


# ----------------------------------------------------------------------
class TestVersioning:
    @pytest.fixture
    async def document(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> dict[str, Any]:
        return await upload(
            client, auth_headers, category=category, document_type=document_type, owner=employee
        )

    async def test_a_new_version_does_not_replace_the_old_one(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        document: dict[str, Any],
        storage_root: Path,
    ) -> None:
        """The promise the whole module rests on."""
        response = await client.post(
            f"{BASE}/{document['id']}/versions",
            data={"notes": "Renewed"},
            files={"file": ("passport-v2.pdf", PDF + b"v2", "application/pdf")},
            headers=auth_headers,
        )

        assert response.status_code == 201
        assert response.json()["data"]["version_count"] == 2

        # Both files are still on disk.
        stored = [path for path in storage_root.rglob("*.pdf") if path.is_file()]
        assert len(stored) == 2
        assert {path.read_bytes() for path in stored} == {PDF, PDF + b"v2"}

    async def test_the_previous_version_is_still_downloadable(
        self, client: AsyncClient, auth_headers: dict[str, str], document: dict[str, Any]
    ) -> None:
        first_version_id = document["current_version"]["id"]

        await client.post(
            f"{BASE}/{document['id']}/versions",
            files={"file": ("v2.pdf", PDF + b"v2", "application/pdf")},
            headers=auth_headers,
        )

        response = await client.get(
            f"{BASE}/{document['id']}/download",
            params={"version_id": first_version_id},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.content == PDF

    async def test_version_numbers_increment(
        self, client: AsyncClient, auth_headers: dict[str, str], document: dict[str, Any]
    ) -> None:
        for index in range(2, 5):
            await client.post(
                f"{BASE}/{document['id']}/versions",
                files={"file": (f"v{index}.pdf", PDF + str(index).encode(), "application/pdf")},
                headers=auth_headers,
            )

        history = (await client.get(f"{BASE}/{document['id']}/versions", headers=auth_headers)).json()["data"]

        assert [row["version_number"] for row in history] == [4, 3, 2, 1]

    async def test_refuses_a_byte_identical_re_upload(
        self, client: AsyncClient, auth_headers: dict[str, str], document: dict[str, Any]
    ) -> None:
        """A double-click is a mistake, not a new version."""
        response = await client.post(
            f"{BASE}/{document['id']}/versions",
            files={"file": ("same.pdf", PDF, "application/pdf")},
            headers=auth_headers,
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "duplicate_version"
        assert "version 1" in response.json()["message"]

    async def test_there_is_no_endpoint_that_edits_a_version(
        self, client: AsyncClient, auth_headers: dict[str, str], document: dict[str, Any]
    ) -> None:
        url = f"{BASE}/{document['id']}/versions"
        assert (await client.patch(url, json={}, headers=auth_headers)).status_code == 405
        assert (await client.delete(url, headers=auth_headers)).status_code == 405
        assert (await client.put(url, json={}, headers=auth_headers)).status_code == 405


# ----------------------------------------------------------------------
class TestDownloadAndPreview:
    @pytest.fixture
    async def document(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> dict[str, Any]:
        return await upload(
            client, auth_headers, category=category, document_type=document_type, owner=employee
        )

    async def test_downloads_as_an_attachment(
        self, client: AsyncClient, auth_headers: dict[str, str], document: dict[str, Any]
    ) -> None:
        response = await client.get(f"{BASE}/{document['id']}/download", headers=auth_headers)

        assert response.status_code == 200
        assert response.content == PDF
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment" in response.headers["content-disposition"]

    async def test_previews_inline(
        self, client: AsyncClient, auth_headers: dict[str, str], document: dict[str, Any]
    ) -> None:
        response = await client.get(f"{BASE}/{document['id']}/preview", headers=auth_headers)

        assert response.status_code == 200
        assert "inline" in response.headers["content-disposition"]
        # Served inline, so it must not be able to reach the app's own origin.
        assert "default-src 'none'" in response.headers["content-security-policy"]

    async def test_sets_nosniff(
        self, client: AsyncClient, auth_headers: dict[str, str], document: dict[str, Any]
    ) -> None:
        """The type came from the file's own signature; nothing to second-guess."""
        response = await client.get(f"{BASE}/{document['id']}/download", headers=auth_headers)
        assert response.headers["x-content-type-options"] == "nosniff"

    async def test_a_version_from_another_document_is_not_readable(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
        document: dict[str, Any],
    ) -> None:
        """Version lookups are scoped, so a known id is not a way in."""
        other = await upload(
            client,
            auth_headers,
            category=category,
            document_type=document_type,
            owner=employee,
            content=PNG,
            filename="other.png",
        )

        response = await client.get(
            f"{BASE}/{document['id']}/download",
            params={"version_id": other["current_version"]["id"]},
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_a_download_is_audited(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        document: dict[str, Any],
    ) -> None:
        await client.get(f"{BASE}/{document['id']}/download", headers=auth_headers)

        entries = (
            (await db_session.execute(select(AuditLog).where(AuditLog.action == "document.downloaded")))
            .scalars()
            .all()
        )
        assert len(entries) == 1
        assert entries[0].entity_id == document["id"]

    async def test_a_preview_is_audited_separately_from_a_download(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        document: dict[str, Any],
    ) -> None:
        """Previewing is browsing; downloading takes a copy out of the vault."""
        await client.get(f"{BASE}/{document['id']}/preview", headers=auth_headers)

        actions = {
            row.action
            for row in (
                (await db_session.execute(select(AuditLog).where(AuditLog.action.like("document.%"))))
                .scalars()
                .all()
            )
        }
        assert "document.previewed" in actions
        assert "document.downloaded" not in actions


# ----------------------------------------------------------------------
class TestNoPathLeak:
    async def test_no_response_carries_a_storage_key(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
        storage_root: Path,
    ) -> None:
        """The API must never reveal where a file physically lives."""
        created = await upload(
            client, auth_headers, category=category, document_type=document_type, owner=employee
        )

        responses = [
            await client.get(BASE, headers=auth_headers),
            await client.get(f"{BASE}/{created['id']}", headers=auth_headers),
            await client.get(f"{BASE}/{created['id']}/versions", headers=auth_headers),
        ]

        for response in responses:
            assert "storage_key" not in response.text
            assert str(storage_root) not in response.text
            assert "uploads" not in response.text.lower()


# ----------------------------------------------------------------------
class TestListing:
    async def test_filters_by_owner(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        await upload(client, auth_headers, category=category, document_type=document_type, owner=employee)

        response = await client.get(
            BASE,
            params={"owner_type": "employee", "owner_id": str(employee.id)},
            headers=auth_headers,
        )
        assert response.json()["data"]["meta"]["total_items"] == 1

        empty = await client.get(BASE, params={"owner_id": str(uuid.uuid4())}, headers=auth_headers)
        assert empty.json()["data"]["meta"]["total_items"] == 0

    async def test_filters_by_expiry_state(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        from datetime import date, timedelta

        today = date.today()
        await upload(
            client,
            auth_headers,
            category=category,
            document_type=document_type,
            owner=employee,
            expiry_date=(today - timedelta(days=1)).isoformat(),
        )
        await upload(
            client,
            auth_headers,
            category=category,
            document_type=document_type,
            owner=employee,
            content=PNG,
            filename="a.png",
            expiry_date=(today + timedelta(days=10)).isoformat(),
        )
        await upload(
            client,
            auth_headers,
            category=category,
            document_type=document_type,
            owner=employee,
            content=JPEG,
            filename="b.jpg",
            expiry_date=(today + timedelta(days=365)).isoformat(),
        )

        for state, expected in [("expired", 1), ("expiring_soon", 1), ("valid", 1)]:
            response = await client.get(BASE, params={"expiry_state": state}, headers=auth_headers)
            assert response.json()["data"]["meta"]["total_items"] == expected, state

    async def test_reports_the_derived_expiry_state(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        from datetime import date, timedelta

        data = await upload(
            client,
            auth_headers,
            category=category,
            document_type=document_type,
            owner=employee,
            expiry_date=(date.today() + timedelta(days=5)).isoformat(),
        )
        assert data["expiry_state"] == "expiring_soon"

    async def test_rejects_an_unsupported_sort_column(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(BASE, params={"sort_by": "storage_key"}, headers=auth_headers)
        assert response.status_code == 400
        assert response.json()["errors"][0]["code"] == "invalid_sort_field"


# ----------------------------------------------------------------------
class TestLifecycle:
    @pytest.fixture
    async def document(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> dict[str, Any]:
        return await upload(
            client, auth_headers, category=category, document_type=document_type, owner=employee
        )

    async def test_records_a_review(
        self, client: AsyncClient, auth_headers: dict[str, str], document: dict[str, Any]
    ) -> None:
        response = await client.post(
            f"{BASE}/{document['id']}/review",
            json={"status": "approved", "review_notes": "Verified against the original."},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "approved"
        assert data["reviewed_at"] is not None

    async def test_a_review_cannot_set_a_derived_status(
        self, client: AsyncClient, auth_headers: dict[str, str], document: dict[str, Any]
    ) -> None:
        """`expired` comes from a date and `archived` has its own endpoint."""
        for status_name in ("expired", "archived"):
            response = await client.post(
                f"{BASE}/{document['id']}/review",
                json={"status": status_name},
                headers=auth_headers,
            )
            assert response.status_code == 422, status_name

    async def test_archives_and_restores(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        document: dict[str, Any],
        storage_root: Path,
    ) -> None:
        archived = await client.post(f"{BASE}/{document['id']}/archive", headers=auth_headers)
        assert archived.json()["data"]["deleted_at"] is not None

        # The file is untouched: archiving hides a record, it does not delete.
        assert len([p for p in storage_root.rglob("*.pdf") if p.is_file()]) == 1

        restored = await client.post(f"{BASE}/{document['id']}/restore", headers=auth_headers)
        assert restored.json()["data"]["deleted_at"] is None

    async def test_an_archived_document_cannot_be_edited(
        self, client: AsyncClient, auth_headers: dict[str, str], document: dict[str, Any]
    ) -> None:
        await client.post(f"{BASE}/{document['id']}/archive", headers=auth_headers)

        response = await client.patch(
            f"{BASE}/{document['id']}", json={"name": "Renamed"}, headers=auth_headers
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "record_archived"

    async def test_updates_metadata(
        self, client: AsyncClient, auth_headers: dict[str, str], document: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"{BASE}/{document['id']}",
            json={"name": "Passport (renewed)", "description": "Issued 2026"},
            headers=auth_headers,
        )
        assert response.json()["data"]["name"] == "Passport (renewed)"


# ----------------------------------------------------------------------
class TestDashboard:
    async def test_reports_the_headline_figures(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        await upload(client, auth_headers, category=category, document_type=document_type, owner=employee)

        data = (await client.get(f"{BASE}/dashboard", headers=auth_headers)).json()["data"]

        assert data["total_documents"] == 1
        assert data["pending_review"] == 1
        assert data["total_storage_bytes"] == len(PDF)
        assert data["by_category"] == [{"label": category.name, "count": 1}]

    async def test_storage_includes_superseded_versions(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        """Superseded versions are what the vault is still holding."""
        document = await upload(
            client, auth_headers, category=category, document_type=document_type, owner=employee
        )
        await client.post(
            f"{BASE}/{document['id']}/versions",
            files={"file": ("v2.pdf", PDF + b"v2", "application/pdf")},
            headers=auth_headers,
        )

        data = (await client.get(f"{BASE}/dashboard", headers=auth_headers)).json()["data"]
        assert data["total_storage_bytes"] == len(PDF) + len(PDF + b"v2")

    async def test_the_dashboard_route_is_not_captured_by_the_id_route(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        assert (await client.get(f"{BASE}/dashboard", headers=auth_headers)).status_code == 200


# ----------------------------------------------------------------------
class TestCategoriesAndTypes:
    async def test_categories_use_the_shared_master_contract(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        base = f"{settings.API_V1_PREFIX}/document-categories"

        created = await client.post(
            base, json={"name": "Medical Records", "code": "MEDICAL"}, headers=auth_headers
        )
        assert created.status_code == 201

        record_id = created.json()["data"]["id"]
        assert (await client.get(f"{base}/{record_id}", headers=auth_headers)).status_code == 200
        assert (
            await client.patch(f"{base}/{record_id}", json={"name": "Medical"}, headers=auth_headers)
        ).status_code == 200
        assert (await client.post(f"{base}/{record_id}/archive", headers=auth_headers)).status_code == 200
        assert (await client.post(f"{base}/{record_id}/restore", headers=auth_headers)).status_code == 200

    async def test_a_category_with_documents_cannot_be_archived(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        await upload(client, auth_headers, category=category, document_type=document_type, owner=employee)

        response = await client.post(
            f"{settings.API_V1_PREFIX}/document-categories/{category.id}/archive",
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "has_active_children"

    async def test_a_type_narrowing_cannot_widen_the_platform_allowlist(
        self, client: AsyncClient, auth_headers: dict[str, str], category: DocumentCategory
    ) -> None:
        response = await client.post(
            f"{settings.API_V1_PREFIX}/document-types",
            json={
                "name": "Spreadsheet",
                "code": "XLS",
                "category_id": str(category.id),
                "allowed_extensions": ".xlsx",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422


# ----------------------------------------------------------------------
class TestAuditTrail:
    async def test_document_scoped_audit_history_is_exposed(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        document = await upload(
            client, auth_headers, category=category, document_type=document_type, owner=employee
        )

        response = await client.get(f"{BASE}/{document['id']}/audit", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["data"][0]["action"] == "document.uploaded"

    async def test_every_action_is_audited(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        document = await upload(
            client, auth_headers, category=category, document_type=document_type, owner=employee
        )
        await client.post(
            f"{BASE}/{document['id']}/versions",
            files={"file": ("v2.pdf", PDF + b"v2", "application/pdf")},
            headers=auth_headers,
        )
        await client.patch(f"{BASE}/{document['id']}", json={"name": "Renamed"}, headers=auth_headers)
        await client.post(
            f"{BASE}/{document['id']}/review", json={"status": "approved"}, headers=auth_headers
        )
        await client.post(f"{BASE}/{document['id']}/archive", headers=auth_headers)

        actions = {
            row.action
            for row in (
                (await db_session.execute(select(AuditLog).where(AuditLog.action.like("document.%"))))
                .scalars()
                .all()
            )
        }

        assert {
            "document.uploaded",
            "document.version.uploaded",
            "document.updated",
            "document.reviewed",
            "document.archived",
        } <= actions

    async def test_the_trail_never_records_a_storage_key(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        await upload(client, auth_headers, category=category, document_type=document_type, owner=employee)

        entries = (
            (await db_session.execute(select(AuditLog).where(AuditLog.action == "document.uploaded")))
            .scalars()
            .all()
        )
        for entry in entries:
            assert "uploads" not in str(entry.context).lower()
            assert ".pdf" not in (entry.description or "")


# ----------------------------------------------------------------------
# Deactivating a classification
# ----------------------------------------------------------------------
class TestDeactivatedType:
    """A type that is switched off must not freeze the documents already filed under it.

    Deactivating is how an administrator stops a type being *chosen* next time.
    Reading it as "these records are now invalid" made every existing document
    of that type unrenameable and unversionable, which is the opposite of the
    intent -- and unreachable by any other route, since archiving a type in use
    is already refused.
    """

    @pytest.fixture
    async def deactivated(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> dict[str, Any]:
        document = await upload(
            client, auth_headers, category=category, document_type=document_type, owner=employee
        )
        document_type.status = RecordStatus.INACTIVE
        await db_session.flush()
        return document

    async def test_metadata_stays_editable(
        self, client: AsyncClient, auth_headers: dict[str, str], deactivated: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"{BASE}/{deactivated['id']}",
            json={"name": "Passport (renamed)"},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["name"] == "Passport (renamed)"

    async def test_the_edit_form_may_resubmit_the_unchanged_classification(
        self, client: AsyncClient, auth_headers: dict[str, str], deactivated: dict[str, Any]
    ) -> None:
        """The form sends every field, so an unchanged type arrives on every save."""
        response = await client.patch(
            f"{BASE}/{deactivated['id']}",
            json={
                "name": "Passport (resubmitted)",
                "category_id": deactivated["category_id"],
                "document_type_id": deactivated["document_type_id"],
            },
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text

    async def test_a_new_version_is_still_accepted(
        self, client: AsyncClient, auth_headers: dict[str, str], deactivated: dict[str, Any]
    ) -> None:
        response = await client.post(
            f"{BASE}/{deactivated['id']}/versions",
            files={"file": ("passport-v2.pdf", PDF + b"second", "application/pdf")},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["data"]["version_count"] == 2

    async def test_an_inactive_type_still_cannot_be_newly_chosen(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        deactivated: dict[str, Any],
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        """The narrower rule survives: deactivating still removes it from circulation."""
        response = await client.post(
            BASE,
            data=upload_form(category=category, document_type=document_type, owner=employee),
            files={"file": ("passport.pdf", PDF, "application/pdf")},
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "invalid_document_type"

    async def test_re_filing_into_an_inactive_type_is_still_refused(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        db_session: AsyncSession,
        category: DocumentCategory,
        document_type: DocumentType,
        employee: Employee,
    ) -> None:
        """Changing the classification is a fresh choice, and is held to the strict rule."""
        live = DocumentType(
            name="Driving License",
            code=f"DL{uuid.uuid4().hex[:6].upper()}",
            category_id=category.id,
            status=RecordStatus.ACTIVE,
        )
        db_session.add(live)
        await db_session.flush()

        document = await upload(client, auth_headers, category=category, document_type=live, owner=employee)
        document_type.status = RecordStatus.INACTIVE
        await db_session.flush()

        response = await client.patch(
            f"{BASE}/{document['id']}",
            json={"category_id": str(category.id), "document_type_id": str(document_type.id)},
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "invalid_document_type"


# ----------------------------------------------------------------------
# Candidate owners
# ----------------------------------------------------------------------
class TestCandidateOwner:
    """A document can be filed against a candidate, and the candidate is checked.

    ``candidate`` was the one owner type the vault was designed for and the only
    one whose target was never verified -- a leftover from when Recruitment did
    not exist. Onboarding sends people to the upload form with
    ``?owner_type=candidate``, so the type has to work end to end.

    Note the resume a candidate is *created* from is filed against a user, not a
    candidate: it exists before the candidate does. Nothing here changes that.
    """

    @pytest.fixture
    async def candidate(
        self,
        db_session: AsyncSession,
        test_user: User,
        business_unit: BusinessUnit,
        designation: Designation,
        grade: Grade,
        location: Location,
        employment_type: EmploymentType,
    ) -> Candidate:
        requisition = JobRequisition(
            job_title="Vault Engineer",
            hiring_type="new_position",
            request_type="new_position",
            status="approved",
            business_unit_id=business_unit.id,
            location_id=location.id,
            designation_id=designation.id,
            grade_id=grade.id,
            employment_type_id=employment_type.id,
            openings=1,
            experience_min=2,
            skills=["Python"],
            certifications=[],
            budget_approved=True,
            hiring_manager_id=test_user.id,
            second_approver_id=test_user.id,
            hr_approver_id=test_user.id,
            target_joining_date=date.today() + timedelta(days=30),
            priority="high",
            responsibilities="Keep files safe",
            requirements="Python",
            working_model="hybrid",
            business_justification="Growth",
        )
        # Both names and the stage sequence are unique, so they are randomised:
        # the seeded rows are already present in a database built by migration.
        source = CandidateSource(name=f"Portal {uuid.uuid4().hex[:6]}")
        stage = RecruitmentStage(
            name=f"Applied {uuid.uuid4().hex[:6]}",
            sequence=900 + (uuid.uuid4().int % 90),
        )
        db_session.add_all([requisition, source, stage])
        await db_session.flush()

        opening = JobOpening(requisition_id=requisition.id, status="published")
        db_session.add(opening)
        await db_session.flush()

        record = Candidate(
            job_opening_id=opening.id,
            source_id=source.id,
            stage_id=stage.id,
            first_name="Meera",
            last_name="Nair",
            email=f"meera.{uuid.uuid4().hex[:6]}@example.com",
            mobile_number="9800000000",
        )
        db_session.add(record)
        await db_session.flush()
        return record

    async def test_a_candidate_document_is_accepted_and_named(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        candidate: Candidate,
    ) -> None:
        response = await client.post(
            BASE,
            data={
                "name": "Aadhaar",
                "category_id": str(category.id),
                "document_type_id": str(document_type.id),
                "owner_type": "candidate",
                "owner_id": str(candidate.id),
            },
            files={"file": ("aadhaar.pdf", PDF, "application/pdf")},
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text

        owner = response.json()["data"]["owner"]
        assert owner["owner_type"] == "candidate"
        # A bare UUID is unusable in a list, so the owner resolves to a name.
        assert owner["display_name"] == "Meera Nair"
        assert owner["reference_code"] == candidate.candidate_code

    async def test_an_unknown_candidate_is_refused(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
    ) -> None:
        response = await client.post(
            BASE,
            data={
                "name": "Aadhaar",
                "category_id": str(category.id),
                "document_type_id": str(document_type.id),
                "owner_type": "candidate",
                "owner_id": str(uuid.uuid4()),
            },
            files={"file": ("aadhaar.pdf", PDF, "application/pdf")},
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "invalid_owner"

    async def test_candidate_documents_can_be_filtered_by_owner(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        category: DocumentCategory,
        document_type: DocumentType,
        candidate: Candidate,
        employee: Employee,
    ) -> None:
        await client.post(
            BASE,
            data={
                "name": "Aadhaar",
                "category_id": str(category.id),
                "document_type_id": str(document_type.id),
                "owner_type": "candidate",
                "owner_id": str(candidate.id),
            },
            files={"file": ("aadhaar.pdf", PDF, "application/pdf")},
            headers=auth_headers,
        )
        await upload(client, auth_headers, category=category, document_type=document_type, owner=employee)

        response = await client.get(
            BASE,
            params={"owner_type": "candidate", "owner_id": str(candidate.id)},
            headers=auth_headers,
        )
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["owner"]["display_name"] == "Meera Nair"
