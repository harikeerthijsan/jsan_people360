"""Employee request/response schemas.

Three things here are worth knowing before reading the rest.

**Sensitive values are masked by the read model, not by the caller.** There is no
code path that returns an employee with a full Aadhaar or account number:
:class:`EmployeeBankRead` and :class:`EmployeeIdentificationRead` mask on
construction. The unmasked forms are separate classes returned by exactly one
endpoint, which audits the access.

**Person-level rules are imported from** :mod:`app.schemas.user`. A name, a
mobile number and a date of birth mean the same thing whether the person is a
login account or an employee, and two copies of those rules would drift.

**Normalisation is attached to the types.** A field cannot be declared without
it, which is the failure mode that lets " ABCDE1234F " and "abcde1234f" both
reach the database and defeat the uniqueness check.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import (
    AddressType,
    BloodGroup,
    EmploymentChangeType,
    EmploymentStatus,
    Gender,
    MaritalStatus,
    WorkMode,
)
from app.schemas.masters import (
    MasterSummary,
    PagedListParams,
    normalise_name,
    normalise_optional_text,
)
from app.schemas.user import BirthDate, MobileNumber, PersonName, PhotoUrl
from app.utils.masking import mask_aadhaar, mask_account_number, mask_pan, mask_tail
from app.utils.strings import collapse_whitespace, normalise_email

# ----------------------------------------------------------------------
# Statutory identifier formats
#
# Shape checks only. None of these is verified against the issuing authority --
# that needs an integration, and a shape check still catches the transposed digit
# and the pasted-wrong-field mistakes that make up almost all real errors.
# ----------------------------------------------------------------------
#: Aadhaar is 12 digits and never begins with 0 or 1, which is what distinguishes
#: it from the many other 12-digit numbers someone might paste into the field.
AADHAAR_PATTERN = re.compile(r"^[2-9][0-9]{11}$")
PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
#: Four letters, a mandatory zero, then six alphanumerics.
IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
UAN_PATTERN = re.compile(r"^[0-9]{12}$")
ESI_PATTERN = re.compile(r"^[0-9]{17}$")
#: Establishment PF numbers vary by region (``MH/BAN/0012345/000/0012345``), so
#: this validates the character set and nothing more.
PF_PATTERN = re.compile(r"^[A-Z0-9/\-]{5,30}$")
#: Passport formats differ by country; employees are not all Indian nationals.
PASSPORT_PATTERN = re.compile(r"^[A-Z0-9]{6,20}$")
DRIVING_LICENSE_PATTERN = re.compile(r"^[A-Z0-9\- ]{6,25}$")
#: Deliberately permissive: postal codes are alphanumeric in half the world.
POSTAL_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9 \-]{1,18}$")

_SEPARATORS = re.compile(r"[\s\-]")


def _strip_separators(value: str) -> str:
    """Remove the spaces and hyphens people type into identifier fields."""
    return _SEPARATORS.sub("", value)


def _upper_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = collapse_whitespace(value).upper()
    return cleaned or None


def validate_aadhaar(value: str | None) -> str | None:
    """Normalise ``1234 5678 9012`` to ``123456789012`` and shape-check it."""
    if value is None:
        return None
    cleaned = _strip_separators(collapse_whitespace(value))
    if not cleaned:
        return None
    if not AADHAAR_PATTERN.match(cleaned):
        raise ValueError("Aadhaar must be 12 digits and cannot start with 0 or 1.")
    return cleaned


def validate_employee_pan(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _upper_or_none(_strip_separators(value))
    if cleaned is None:
        return None
    if not PAN_PATTERN.match(cleaned):
        raise ValueError("PAN must be 5 letters, 4 digits and a letter, for example ABCDE1234F.")
    return cleaned


def validate_ifsc(value: str) -> str:
    cleaned = _strip_separators(collapse_whitespace(value)).upper()
    if not IFSC_PATTERN.match(cleaned):
        raise ValueError(
            "IFSC must be 4 letters, a zero and 6 alphanumeric characters, for example HDFC0001234."
        )
    return cleaned


def validate_account_number(value: str) -> str:
    cleaned = _strip_separators(collapse_whitespace(value)).upper()
    if not cleaned.isalnum() or not 6 <= len(cleaned) <= 34:
        raise ValueError("Account number must be 6 to 34 letters or digits.")
    return cleaned


def _optional_pattern(pattern: re.Pattern[str], message: str) -> Any:
    """Build a validator for an optional, upper-cased, separator-free identifier."""

    def _validate(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _upper_or_none(_strip_separators(value))
        if cleaned is None:
            return None
        if not pattern.match(cleaned):
            raise ValueError(message)
        return cleaned

    return _validate


validate_uan = _optional_pattern(UAN_PATTERN, "UAN must be exactly 12 digits.")
validate_esi = _optional_pattern(ESI_PATTERN, "ESI number must be exactly 17 digits.")
validate_pf = _optional_pattern(
    PF_PATTERN, "PF number may contain only letters, digits, slashes and hyphens."
)
validate_passport = _optional_pattern(PASSPORT_PATTERN, "Passport number must be 6 to 20 letters or digits.")


def validate_driving_license(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _upper_or_none(value)
    if cleaned is None:
        return None
    if not DRIVING_LICENSE_PATTERN.match(cleaned):
        raise ValueError("Driving licence number may contain only letters, digits, spaces and hyphens.")
    return cleaned


def validate_postal_code(value: str) -> str:
    cleaned = collapse_whitespace(value).upper()
    if not POSTAL_CODE_PATTERN.match(cleaned):
        raise ValueError("Enter a valid postal code.")
    return cleaned


def validate_joining_date(value: date) -> date:
    """Reject a joining date implausibly far from today.

    Future dates are allowed -- pre-boarding an employee before their start is
    the normal case -- but only within a year, which catches the mistyped year
    without blocking legitimate planning.
    """
    today = date.today()
    if value.year < 1950:
        raise ValueError("Joining date is implausibly far in the past; check the year.")
    if (value - today).days > 365:
        raise ValueError("Joining date cannot be more than a year in the future.")
    return value


# ----------------------------------------------------------------------
# Field types
# ----------------------------------------------------------------------
Nationality = Annotated[
    str | None, Field(default=None, max_length=100), AfterValidator(normalise_optional_text)
]
ShortText = Annotated[
    str | None, Field(default=None, max_length=150), AfterValidator(normalise_optional_text)
]
Relationship = Annotated[
    str | None, Field(default=None, max_length=50), AfterValidator(normalise_optional_text)
]
ExtensionNumber = Annotated[
    str | None, Field(default=None, max_length=20), AfterValidator(normalise_optional_text)
]
JoiningDate = Annotated[date, AfterValidator(validate_joining_date)]
AddressLine = Annotated[str, Field(min_length=3, max_length=255), AfterValidator(normalise_name)]
PlaceField = Annotated[str, Field(min_length=1, max_length=100), AfterValidator(normalise_name)]
PostalCode = Annotated[str, Field(min_length=2, max_length=20), AfterValidator(validate_postal_code)]
IfscCode = Annotated[str, Field(min_length=11, max_length=11), AfterValidator(validate_ifsc)]
AccountNumber = Annotated[str, Field(min_length=6, max_length=34), AfterValidator(validate_account_number)]
Ctc = Annotated[
    Decimal | None,
    Field(default=None, ge=0, max_digits=14, decimal_places=2, description="Annual cost to company."),
]
ChangeReason = Annotated[
    str | None, Field(default=None, max_length=500), AfterValidator(normalise_optional_text)
]
LongNotes = Annotated[
    str | None, Field(default=None, max_length=5000), AfterValidator(normalise_optional_text)
]

EMPLOYEE_MODEL_CONFIG = ConfigDict(str_strip_whitespace=True, extra="forbid")


# ----------------------------------------------------------------------
# Address
# ----------------------------------------------------------------------
class EmployeeAddressInput(BaseModel):
    """One address supplied on create or update."""

    model_config = EMPLOYEE_MODEL_CONFIG

    address_type: AddressType
    address_line1: AddressLine
    address_line2: ShortText = None
    landmark: ShortText = None
    city: PlaceField
    state: PlaceField
    country: PlaceField
    postal_code: PostalCode


class EmployeeAddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    address_type: AddressType
    address_line1: str
    address_line2: str | None = None
    landmark: str | None = None
    city: str
    state: str
    country: str
    postal_code: str


# ----------------------------------------------------------------------
# Bank details
# ----------------------------------------------------------------------
class EmployeeBankInput(BaseModel):
    model_config = EMPLOYEE_MODEL_CONFIG

    bank_name: Annotated[str, Field(min_length=2, max_length=150), AfterValidator(normalise_name)]
    account_number: AccountNumber
    account_holder_name: ShortText = None
    ifsc_code: IfscCode
    branch_name: Annotated[str, Field(min_length=2, max_length=150), AfterValidator(normalise_name)]


class EmployeeBankRead(BaseModel):
    """Bank details as returned by every ordinary read.

    ``account_number`` is masked here rather than by the caller, so there is no
    way to return an employee and forget to mask it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bank_name: str
    account_number: str = Field(description="Masked; the last four digits only.")
    account_holder_name: str | None = None
    ifsc_code: str = Field(description="Not masked: a branch code identifies a bank, not a person.")
    branch_name: str

    @field_validator("account_number", mode="before")
    @classmethod
    def _mask(cls, value: str | None) -> str | None:
        return mask_account_number(value)


class EmployeeBankReveal(EmployeeBankInput):
    """Unmasked bank details. Returned by the audited reveal endpoint only."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


# ----------------------------------------------------------------------
# Government identifiers
# ----------------------------------------------------------------------
class EmployeeIdentificationInput(BaseModel):
    model_config = EMPLOYEE_MODEL_CONFIG

    aadhaar_number: Annotated[
        str | None, Field(default=None, max_length=20), AfterValidator(validate_aadhaar)
    ] = None
    pan_number: Annotated[
        str | None, Field(default=None, max_length=15), AfterValidator(validate_employee_pan)
    ] = None
    passport_number: Annotated[
        str | None, Field(default=None, max_length=20), AfterValidator(validate_passport)
    ] = None
    passport_expiry: Annotated[
        str | None, Field(default=None, max_length=10), AfterValidator(normalise_optional_text)
    ] = None
    driving_license_number: Annotated[
        str | None, Field(default=None, max_length=25), AfterValidator(validate_driving_license)
    ] = None
    uan_number: Annotated[str | None, Field(default=None, max_length=15), AfterValidator(validate_uan)] = None
    pf_number: Annotated[str | None, Field(default=None, max_length=30), AfterValidator(validate_pf)] = None
    esi_number: Annotated[str | None, Field(default=None, max_length=20), AfterValidator(validate_esi)] = None


class EmployeeIdentificationRead(BaseModel):
    """Identifiers as returned by every ordinary read.

    Aadhaar, PAN, passport and driving licence are masked: each identifies the
    person rather than the employment, and each is enough on its own to open an
    account somewhere. UAN, PF and ESI numbers are not masked -- they are
    employer-side reference numbers that already appear on every payslip, and
    masking them would make the payroll reconciliation this screen exists for
    impossible without a reveal.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    aadhaar_number: str | None = None
    pan_number: str | None = None
    passport_number: str | None = None
    passport_expiry: str | None = None
    driving_license_number: str | None = None
    uan_number: str | None = None
    pf_number: str | None = None
    esi_number: str | None = None

    @field_validator("aadhaar_number", mode="before")
    @classmethod
    def _mask_aadhaar(cls, value: str | None) -> str | None:
        return mask_aadhaar(value)

    @field_validator("pan_number", mode="before")
    @classmethod
    def _mask_pan(cls, value: str | None) -> str | None:
        return mask_pan(value)

    @field_validator("passport_number", "driving_license_number", mode="before")
    @classmethod
    def _mask_document(cls, value: str | None) -> str | None:
        return mask_tail(value, visible=3)


class EmployeeIdentificationReveal(EmployeeIdentificationInput):
    """Unmasked identifiers. Returned by the audited reveal endpoint only."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class EmployeeSensitiveReveal(BaseModel):
    """Everything an edit form needs and no ordinary read returns."""

    employee_id: uuid.UUID
    bank_detail: EmployeeBankReveal | None = None
    identification: EmployeeIdentificationReveal | None = None


# ----------------------------------------------------------------------
# Write schemas
# ----------------------------------------------------------------------
class EmployeePersonalFields(BaseModel):
    """The person, independent of their employment."""

    model_config = EMPLOYEE_MODEL_CONFIG

    gender: Gender | None = None
    date_of_birth: BirthDate = None
    blood_group: BloodGroup | None = None
    marital_status: MaritalStatus | None = None
    nationality: Nationality = None

    personal_email: EmailStr | None = None
    mobile_number: MobileNumber = None
    alternate_number: MobileNumber = None

    emergency_contact_name: ShortText = None
    emergency_contact_number: MobileNumber = None
    emergency_contact_relationship: Relationship = None

    photo_url: PhotoUrl = None

    @field_validator("personal_email")
    @classmethod
    def _normalise_personal_email(cls, value: str | None) -> str | None:
        return normalise_email(value) if value else None


class EmployeeEmploymentFields(BaseModel):
    """Where the person sits in the organization, and on what terms.

    Every reference is optional for the same reason as on ``users``: the org tree
    may not be complete when the first employee is recorded, and requiring a
    business unit would make the first save impossible against a fresh database.
    """

    model_config = EMPLOYEE_MODEL_CONFIG

    employment_type_id: uuid.UUID | None = None
    business_unit_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    grade_id: uuid.UUID | None = None
    work_location_id: uuid.UUID | None = None
    reporting_manager_id: uuid.UUID | None = None

    official_mobile: MobileNumber = None
    extension_number: ExtensionNumber = None
    work_mode: WorkMode | None = None

    ctc: Ctc = None
    salary_grade_id: uuid.UUID | None = None
    notes: LongNotes = None


class EmployeeCreate(EmployeePersonalFields, EmployeeEmploymentFields):
    """Payload for recording a new employee.

    ``employee_code`` is absent by design: the database generates it, and a
    client can neither supply nor edit one.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "first_name": "Priya",
                "last_name": "Sharma",
                "official_email": "priya.sharma@jsan.example",
                "joining_date": "2026-08-01",
                "employment_status": "probation",
                "gender": "female",
                "date_of_birth": "1994-06-15",
                "mobile_number": "+91 98765 43210",
                "work_mode": "hybrid",
            }
        },
    )

    first_name: PersonName
    last_name: PersonName
    official_email: EmailStr = Field(description="Work address. Unique across employees.")
    joining_date: JoiningDate

    user_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "The login account for this person. Optional: an employee can be "
            "recorded before an account exists. When supplied, the account must "
            "not already belong to another employee."
        ),
    )
    employment_status: EmploymentStatus = EmploymentStatus.PROBATION

    addresses: list[EmployeeAddressInput] = Field(
        default_factory=list, max_length=2, description="At most one current and one permanent address."
    )
    bank_detail: EmployeeBankInput | None = None
    identification: EmployeeIdentificationInput | None = None

    @field_validator("official_email")
    @classmethod
    def _normalise_official_email(cls, value: str) -> str:
        return normalise_email(value)

    @field_validator("addresses")
    @classmethod
    def _unique_address_types(cls, value: list[EmployeeAddressInput]) -> list[EmployeeAddressInput]:
        kinds = [item.address_type for item in value]
        if len(set(kinds)) != len(kinds):
            raise ValueError("An employee can have only one address of each type.")
        return value


class EmployeeUpdate(EmployeePersonalFields, EmployeeEmploymentFields):
    """Partial update by an administrator; omitted fields are unchanged.

    ``employment_status``, ``team_id``, ``designation_id``, ``grade_id``,
    ``reporting_manager_id`` and ``work_location_id`` are accepted here, and a
    change to any of them writes an employment-history row exactly as the
    dedicated lifecycle endpoints do. Leaving them off this schema would only
    push administrators towards editing the database directly.
    """

    first_name: PersonName | None = None
    last_name: PersonName | None = None
    official_email: EmailStr | None = None
    joining_date: JoiningDate | None = None
    user_id: uuid.UUID | None = None
    employment_status: EmploymentStatus | None = None

    #: Why the placement changed, recorded on any history row this update
    #: produces. Not a column on ``employees``.
    change_reason: ChangeReason = None

    @field_validator("official_email")
    @classmethod
    def _normalise_official_email(cls, value: str | None) -> str | None:
        return normalise_email(value) if value else None


# ----------------------------------------------------------------------
# Lifecycle payloads
#
# One small schema per action rather than a general "update" with a mode flag:
# a promotion and a transfer need different fields, and a shared schema would
# make every field optional and every rule conditional.
# ----------------------------------------------------------------------
class LifecycleBase(BaseModel):
    model_config = EMPLOYEE_MODEL_CONFIG

    effective_date: date = Field(
        default_factory=date.today,
        description="When the change takes effect. Defaults to today; back-dating is allowed.",
    )
    reason: ChangeReason = None
    notes: LongNotes = None


class ConfirmEmployeeRequest(LifecycleBase):
    """Confirm an employee at the end of probation."""


class TransferTeamRequest(LifecycleBase):
    team_id: uuid.UUID
    business_unit_id: uuid.UUID | None = Field(
        default=None,
        description="Supply when the move also crosses business units.",
    )


class ChangeDesignationRequest(LifecycleBase):
    designation_id: uuid.UUID
    grade_id: uuid.UUID | None = None


class ChangeManagerRequest(LifecycleBase):
    reporting_manager_id: uuid.UUID | None = Field(
        default=None, description="Null clears the reporting line, for example for the CEO."
    )


class PromoteEmployeeRequest(LifecycleBase):
    """A promotion: a new designation, grade, pay band or salary -- or several.

    Every field is optional individually but the payload cannot be empty: a
    promotion that changes nothing is a history row with no content, which is
    worse than an error because it looks like a record of something.
    """

    designation_id: uuid.UUID | None = None
    grade_id: uuid.UUID | None = None
    salary_grade_id: uuid.UUID | None = None
    ctc: Ctc = None

    @model_validator(mode="after")
    def _require_a_change(self) -> PromoteEmployeeRequest:
        if not any((self.designation_id, self.grade_id, self.salary_grade_id, self.ctc)):
            raise ValueError(
                "A promotion must change at least one of designation, grade, salary grade or CTC."
            )
        return self


class ChangeStatusRequest(LifecycleBase):
    employment_status: EmploymentStatus


class ChangeLocationRequest(LifecycleBase):
    work_location_id: uuid.UUID | None = None
    work_mode: WorkMode | None = None


# ----------------------------------------------------------------------
# Read schemas
# ----------------------------------------------------------------------
class EmployeeSummary(BaseModel):
    """Compact employee reference, embedded in other payloads."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    full_name: str
    official_email: EmailStr
    photo_url: str | None = None
    employment_status: EmploymentStatus


class EmployeeOrganization(BaseModel):
    """Resolved organizational placement, with names rather than bare ids."""

    model_config = ConfigDict(from_attributes=True)

    business_unit: MasterSummary | None = None
    team: MasterSummary | None = None
    designation: MasterSummary | None = None
    grade: MasterSummary | None = None
    salary_grade: MasterSummary | None = None
    work_location: MasterSummary | None = None
    employment_type: MasterSummary | None = None


class UserLink(BaseModel):
    """The login account attached to an employee, if any."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_code: str
    username: str
    email: EmailStr
    is_active: bool


class EmployeeRead(BaseModel):
    """Full representation of an employee.

    Assembled by :meth:`from_employee` rather than straight validation, because
    three of its fields are projections -- the derived name, the resolved
    organization, and the two sensitive blocks, which are masked on the way out.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str

    first_name: str
    last_name: str
    full_name: str = Field(description="Derived from the name parts, never stored.")

    gender: Gender | None = None
    date_of_birth: date | None = None
    blood_group: BloodGroup | None = None
    marital_status: MaritalStatus | None = None
    nationality: str | None = None

    personal_email: EmailStr | None = None
    mobile_number: str | None = None
    alternate_number: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_number: str | None = None
    emergency_contact_relationship: str | None = None
    photo_url: str | None = None

    official_email: EmailStr
    official_mobile: str | None = None
    extension_number: str | None = None
    work_mode: WorkMode | None = None

    joining_date: date
    confirmation_date: date | None = None
    employment_status: EmploymentStatus

    employment_type_id: uuid.UUID | None = None
    business_unit_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    grade_id: uuid.UUID | None = None
    work_location_id: uuid.UUID | None = None
    salary_grade_id: uuid.UUID | None = None
    reporting_manager_id: uuid.UUID | None = None

    organization: EmployeeOrganization
    reporting_manager: EmployeeSummary | None = None
    user: UserLink | None = None

    ctc: Decimal | None = None
    notes: str | None = None

    addresses: list[EmployeeAddressRead] = Field(default_factory=list)
    bank_detail: EmployeeBankRead | None = None
    identification: EmployeeIdentificationRead | None = None

    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
    deleted_at: datetime | None = Field(
        default=None, description="Set when the employee is archived; null when live."
    )

    @classmethod
    def from_employee(cls, employee: Any) -> EmployeeRead:
        """Build the response from an ORM employee.

        Every scalar field is read straight off the object, so adding a column to
        both the model and this schema needs no change here. Only the projections
        are assembled explicitly.
        """
        data: dict[str, Any] = {
            name: getattr(employee, name) for name in cls.model_fields if hasattr(employee, name)
        }
        data["organization"] = EmployeeOrganization.model_validate(employee)
        return cls.model_validate(data)


class EmployeeAuditEntry(BaseModel):
    """One audit-trail entry concerning an employee.

    A projection of :class:`~app.models.audit_log.AuditLog` rather than the row
    itself: the trail carries request ids, IP addresses and user agents that
    belong in an operator's investigation, not on a profile page.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    outcome: str
    description: str | None = None
    actor_id: uuid.UUID | None = None
    actor_email: str | None = None
    context: dict[str, Any] | None = None
    created_at: datetime


class EmploymentHistoryRead(BaseModel):
    """One entry of an employee's placement history."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    change_type: EmploymentChangeType
    effective_date: date
    employment_status: EmploymentStatus

    team: MasterSummary | None = None
    designation: MasterSummary | None = None
    grade: MasterSummary | None = None
    work_location: MasterSummary | None = None
    reporting_manager: EmployeeSummary | None = None

    summary: str
    reason: str | None = None
    notes: str | None = None

    created_at: datetime
    created_by: uuid.UUID | None = None


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------
class CountByLabel(BaseModel):
    """One bar of a breakdown chart."""

    label: str
    count: int


class EmployeeDashboardStats(BaseModel):
    """Headline figures for the employee dashboard."""

    total_employees: int = Field(description="Live records, whatever their status.")
    employed: int = Field(description="Probation, confirmed, active or on notice.")
    by_status: list[CountByLabel]
    by_business_unit: list[CountByLabel]
    by_work_mode: list[CountByLabel]
    joining_this_month: int
    on_probation: int
    on_notice: int
    archived: int


# ----------------------------------------------------------------------
# Query parameters
# ----------------------------------------------------------------------
class EmployeeListParams(PagedListParams):
    """The shared list parameters plus everything the advanced filter offers.

    Inherits :class:`PagedListParams` rather than ``MasterListParams``: an
    employee has no ``status`` column, and accepting one would let a client pass
    a filter that is silently ignored.
    """

    # The inherited default is `name`, which employees do not have -- theirs is
    # stored in two columns. Staff-code order is the directory ordering people
    # expect, and it is stable.
    sort_by: str = Field(default="employee_code", max_length=50, description="Column to sort by.")

    employment_status: EmploymentStatus | None = Field(
        default=None, description="Filter by lifecycle status."
    )
    business_unit_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    grade_id: uuid.UUID | None = None
    work_location_id: uuid.UUID | None = None
    employment_type_id: uuid.UUID | None = None
    reporting_manager_id: uuid.UUID | None = None
    work_mode: WorkMode | None = None

    joined_from: date | None = Field(default=None, description="Joining date on or after this date.")
    joined_to: date | None = Field(default=None, description="Joining date on or before this date.")


class ExportFormat(StrEnum):
    """The file formats the directory can be exported as."""

    CSV = "csv"
    XLSX = "xlsx"


class EmployeeExportParams(EmployeeListParams):
    """The list filters plus the file format.

    The format lives on the params model rather than beside it as a second query
    parameter: FastAPI expands a Pydantic model into individual query parameters
    only when it is the sole ``Query()`` annotation on the endpoint, and a
    scalar alongside it silently turns the whole model into one parameter named
    "params".
    """

    export_format: ExportFormat = Field(default=ExportFormat.CSV, alias="format", description="csv or xlsx.")
