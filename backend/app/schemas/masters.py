"""Shared building blocks for the organization master-data schemas.

Nine masters share the same shape -- a name, an optional description, a status,
and for most of them a short code. Declaring that once here is what keeps the
validation rules identical across every master instead of drifting per entity.

Normalisation is attached to the *types* via ``Annotated`` rather than to each
model via ``field_validator``. A field then cannot be declared without its
normalisation, which is the failure mode that lets " GIS " and "GIS" both reach
the database.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.models.enums import RecordStatus
from app.utils.strings import collapse_whitespace

#: Codes are used in URLs, exports and integrations, so the character set is
#: restricted to what survives all three without escaping.
CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]*$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")

# Indian statutory identifiers. Shape-checked only -- neither is verified
# against the issuing authority.
GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")
PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


# ----------------------------------------------------------------------
# Normalisation and validation functions
# ----------------------------------------------------------------------
def normalise_name(value: str) -> str:
    """Collapse internal whitespace runs to a single space.

    Without this, "Web  Development" and "Web Development" are different
    strings, defeat the uniqueness check, and produce duplicate master records.
    Leading and trailing whitespace is already removed by
    ``str_strip_whitespace`` on the model config.
    """
    cleaned = collapse_whitespace(value)
    if not cleaned:
        raise ValueError("Value cannot be blank.")
    return cleaned


def normalise_code(value: str) -> str:
    """Upper-case a code and validate its character set."""
    cleaned = collapse_whitespace(value).upper().replace(" ", "_")
    if not CODE_PATTERN.match(cleaned):
        raise ValueError(
            "Code must start with a letter or digit and contain only letters, "
            "digits, hyphens and underscores."
        )
    return cleaned


def normalise_optional_text(value: str | None) -> str | None:
    """Turn a blank string into ``None``.

    Storing "" and NULL for the same idea makes every downstream check wrong in
    one case or the other.
    """
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def validate_timezone(value: str) -> str:
    """Reject anything that is not a real IANA timezone identifier.

    Attendance, leave and payroll will all resolve times against this value, so
    a typo here becomes a wrong-by-hours bug in three modules later.
    """
    if value not in available_timezones():
        raise ValueError(f"{value!r} is not a recognised IANA timezone identifier.")
    return value


def validate_currency(value: str) -> str:
    """Normalise and shape-check an ISO 4217 alphabetic currency code."""
    cleaned = value.strip().upper()
    if not CURRENCY_PATTERN.match(cleaned):
        raise ValueError("Currency must be a three-letter ISO 4217 code, for example INR.")
    return cleaned


def validate_gstin(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    cleaned = value.strip().upper()
    if not GSTIN_PATTERN.match(cleaned):
        raise ValueError("GST number must be a valid 15-character GSTIN.")
    return cleaned


def validate_pan(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    cleaned = value.strip().upper()
    if not PAN_PATTERN.match(cleaned):
        raise ValueError("PAN must be 5 letters, 4 digits and a letter, for example ABCDE1234F.")
    return cleaned


# ----------------------------------------------------------------------
# Field types
# ----------------------------------------------------------------------
MasterName = Annotated[str, Field(min_length=2, max_length=150), AfterValidator(normalise_name)]
MasterCode = Annotated[str, Field(min_length=2, max_length=50), AfterValidator(normalise_code)]
MasterDescription = Annotated[
    str | None, Field(default=None, max_length=2000), AfterValidator(normalise_optional_text)
]
PlaceName = Annotated[str, Field(min_length=1, max_length=100), AfterValidator(normalise_name)]
AddressText = Annotated[str, Field(min_length=5, max_length=1000)]
TimezoneStr = Annotated[
    str,
    Field(min_length=3, max_length=64, description="IANA timezone identifier, e.g. Asia/Kolkata."),
    AfterValidator(validate_timezone),
]
CurrencyStr = Annotated[
    str,
    Field(min_length=3, max_length=3, description="ISO 4217 alphabetic code, e.g. INR."),
    AfterValidator(validate_currency),
]
SeniorityLevel = Annotated[
    int,
    Field(ge=1, le=99, description="Seniority rank; 1 is the most junior. Ordering only."),
]

MASTER_MODEL_CONFIG = ConfigDict(str_strip_whitespace=True, extra="forbid")


# ----------------------------------------------------------------------
# Write schemas
# ----------------------------------------------------------------------
class MasterCreateBase(BaseModel):
    """Fields common to creating any master record."""

    model_config = MASTER_MODEL_CONFIG

    name: MasterName
    description: MasterDescription = None
    status: RecordStatus = RecordStatus.ACTIVE


class CodedMasterCreateBase(MasterCreateBase):
    """Adds the short stable code that other modules reference."""

    code: MasterCode


class MasterUpdateBase(BaseModel):
    """Partial update. Every field is optional; omitted fields are untouched."""

    model_config = MASTER_MODEL_CONFIG

    name: MasterName | None = None
    description: MasterDescription = None
    status: RecordStatus | None = None


class CodedMasterUpdateBase(MasterUpdateBase):
    code: MasterCode | None = None


# ----------------------------------------------------------------------
# Read schemas
# ----------------------------------------------------------------------
class MasterSummary(BaseModel):
    """Compact reference to a master record, embedded in other payloads.

    List screens need the parent's name, not just its id; embedding it avoids a
    lookup request per row.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str | None = None
    status: RecordStatus


class MasterReadBase(BaseModel):
    """Fields returned for every master record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    status: RecordStatus

    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
    deleted_at: datetime | None = Field(
        default=None, description="Set when the record is archived; null when live."
    )

    @property
    def is_archived(self) -> bool:
        return self.deleted_at is not None


class CodedMasterReadBase(MasterReadBase):
    code: str


# ----------------------------------------------------------------------
# Query parameters
# ----------------------------------------------------------------------
class PagedListParams(BaseModel):
    """Paging, search, archive scoping and sorting.

    Split out from :class:`MasterListParams` so that entities which page and sort
    the same way but have no ``status`` column -- employees have a lifecycle
    status of their own -- can reuse this without inheriting a filter that does
    not apply to them.
    """

    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1, description="1-based page number.")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page.")

    search: str | None = Field(
        default=None,
        max_length=150,
        description="Case-insensitive match across the entity's searchable columns.",
    )
    archived: bool = Field(
        default=False,
        description=(
            "false (default) returns only live records; true returns only archived "
            "ones. Live and archived records are never mixed in one page."
        ),
    )

    sort_by: str = Field(default="name", max_length=50, description="Column to sort by.")
    sort_order: SortOrder = SortOrder.ASC

    @field_validator("search")
    @classmethod
    def _clean_search(cls, value: str | None) -> str | None:
        return normalise_optional_text(value)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def descending(self) -> bool:
        return self.sort_order is SortOrder.DESC


class MasterListParams(PagedListParams):
    """Query parameters shared by every master list endpoint."""

    status: RecordStatus | None = Field(
        default=None, description="Filter by business status. Omit to return both."
    )
