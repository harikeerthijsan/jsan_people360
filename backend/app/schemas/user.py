"""User request/response schemas.

Three audiences, three sets of write schemas:

* :class:`UserCreate` / :class:`UserUpdate` -- what an administrator may set.
* :class:`ProfileUpdate` -- the much smaller set a user may change about
  themselves. Modelling it separately is what makes it impossible for a
  self-service request to touch an organizational assignment: those fields are
  not on the model at all, rather than being stripped out somewhere downstream.
* :class:`AdminPasswordReset` -- an administrator setting someone else's
  password.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import MAX_PASSWORD_BYTES
from app.models.enums import Gender, RecordStatus
from app.schemas.masters import MasterListParams, MasterSummary
from app.utils.strings import collapse_whitespace, normalise_email

# ----------------------------------------------------------------------
# Password policy
# ----------------------------------------------------------------------
PASSWORD_MIN_LENGTH = 8

_PASSWORD_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[a-z]"), "one lowercase letter"),
    (re.compile(r"[A-Z]"), "one uppercase letter"),
    (re.compile(r"\d"), "one digit"),
    (re.compile(r"[^A-Za-z0-9]"), "one special character"),
)


def validate_password_strength(value: str) -> str:
    """Enforce the platform password policy. Shared by every password field."""
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must not exceed {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded.")
    missing = [label for pattern, label in _PASSWORD_RULES if not pattern.search(value)]
    if missing:
        raise ValueError("Password must contain at least " + ", ".join(missing) + ".")
    return value


PasswordStr = Annotated[
    str,
    Field(min_length=PASSWORD_MIN_LENGTH, max_length=MAX_PASSWORD_BYTES),
    AfterValidator(validate_password_strength),
]

# ----------------------------------------------------------------------
# Field types
# ----------------------------------------------------------------------
#: Usernames appear in URLs and audit trails, so the character set is narrow and
#: predictable. Stored lower-cased so the value matches how it is compared.
USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

#: Deliberately permissive: it accepts the international formats people actually
#: type (+91 98765 43210, 020 7946 0958) while rejecting free text. Validating
#: numbers properly needs a library and a country context, neither of which this
#: module has.
MOBILE_PATTERN = re.compile(r"^\+?[0-9][0-9 ()\-]{6,20}$")

MIN_WORKING_AGE = 14
MAX_WORKING_AGE = 100


def normalise_person_name(value: str) -> str:
    cleaned = collapse_whitespace(value)
    if not cleaned:
        raise ValueError("Name cannot be blank.")
    return cleaned


def normalise_username(value: str) -> str:
    cleaned = collapse_whitespace(value).lower().replace(" ", ".")
    if not USERNAME_PATTERN.match(cleaned):
        raise ValueError(
            "Username must start with a letter or digit and contain only lower-case "
            "letters, digits, dots, hyphens and underscores."
        )
    return cleaned


def normalise_mobile(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = collapse_whitespace(value)
    if not cleaned:
        return None
    if not MOBILE_PATTERN.match(cleaned):
        raise ValueError("Enter a valid mobile number, for example +91 98765 43210.")
    return cleaned


def validate_birth_date(value: date | None) -> date | None:
    """Reject birth dates that cannot belong to a working adult.

    A future date is always a typo, and the age bounds catch the far more common
    slip of entering the current year.
    """
    if value is None:
        return None
    today = date.today()
    if value > today:
        raise ValueError("Date of birth cannot be in the future.")

    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    if age < MIN_WORKING_AGE:
        raise ValueError(f"Date of birth implies an age below {MIN_WORKING_AGE}; check the value.")
    if age > MAX_WORKING_AGE:
        raise ValueError(f"Date of birth implies an age above {MAX_WORKING_AGE}; check the value.")
    return value


PersonName = Annotated[str, Field(min_length=1, max_length=100), AfterValidator(normalise_person_name)]
Username = Annotated[str, Field(min_length=3, max_length=50), AfterValidator(normalise_username)]
MobileNumber = Annotated[str | None, Field(default=None, max_length=32), AfterValidator(normalise_mobile)]
BirthDate = Annotated[date | None, Field(default=None), AfterValidator(validate_birth_date)]
PhotoUrl = Annotated[str | None, Field(default=None, max_length=1024)]

USER_MODEL_CONFIG = ConfigDict(str_strip_whitespace=True, extra="forbid")


# ----------------------------------------------------------------------
# Write schemas -- administrator
# ----------------------------------------------------------------------
class UserOrganizationFields(BaseModel):
    """Where a person sits in the organization.

    Every reference is optional: a user can legitimately exist before the org
    tree does, and requiring a business unit would make it impossible to create
    the first account against an empty database.
    """

    model_config = USER_MODEL_CONFIG

    business_unit_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    grade_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    employment_type_id: uuid.UUID | None = None
    joining_date: date | None = None


class UserCreate(UserOrganizationFields):
    """Payload for provisioning a new account.

    ``user_code`` is absent by design: it is generated by the database and can
    never be supplied or edited by a client.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "first_name": "Jane",
                "last_name": "Doe",
                "username": "jane.doe",
                "email": "jane.doe@jsan.example",
                "personal_email": "jane@personal.example",
                "phone_number": "+91 98765 43210",
                "gender": "female",
                "date_of_birth": "1994-06-15",
                "joining_date": "2026-08-01",
                "password": "Str0ng@Pass",
                "status": "active",
            }
        },
    )

    first_name: PersonName
    last_name: PersonName
    username: Username
    email: EmailStr = Field(description="Official email address; also a sign-in identifier.")
    personal_email: EmailStr | None = None
    phone_number: MobileNumber = None
    gender: Gender | None = None
    date_of_birth: BirthDate = None
    avatar_url: PhotoUrl = None

    password: PasswordStr
    force_password_change: bool = Field(
        default=False, description="Require a new password at the next sign-in."
    )
    status: RecordStatus = RecordStatus.ACTIVE

    @field_validator("email", "personal_email")
    @classmethod
    def _normalise_email(cls, value: str | None) -> str | None:
        return normalise_email(value) if value else None


class UserUpdate(UserOrganizationFields):
    """Partial update of an existing account by an administrator.

    ``password`` is absent: setting someone else's password is a separate,
    separately audited operation rather than a field on a general edit.
    """

    first_name: PersonName | None = None
    last_name: PersonName | None = None
    username: Username | None = None
    email: EmailStr | None = None
    personal_email: EmailStr | None = None
    phone_number: MobileNumber = None
    gender: Gender | None = None
    date_of_birth: BirthDate = None
    avatar_url: PhotoUrl = None
    status: RecordStatus | None = None

    @field_validator("email", "personal_email")
    @classmethod
    def _normalise_email(cls, value: str | None) -> str | None:
        return normalise_email(value) if value else None


# ----------------------------------------------------------------------
# Write schemas -- self service
# ----------------------------------------------------------------------
class ProfileUpdate(BaseModel):
    """What a user may change about themselves.

    Names, username, official email, organizational placement and status are all
    absent. They are administrative facts, and leaving them off this model means
    a self-service request cannot carry them at all -- ``extra="forbid"`` turns
    an attempt into a 422 rather than a silently discarded field.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "personal_email": "jane@personal.example",
                "phone_number": "+91 98765 43210",
                "avatar_url": "https://cdn.example/avatars/jane.png",
            }
        },
    )

    personal_email: EmailStr | None = None
    phone_number: MobileNumber = None
    avatar_url: PhotoUrl = None

    @field_validator("personal_email")
    @classmethod
    def _normalise_email(cls, value: str | None) -> str | None:
        return normalise_email(value) if value else None


class AdminPasswordReset(BaseModel):
    """An administrator setting another user's password."""

    model_config = USER_MODEL_CONFIG

    new_password: PasswordStr
    force_password_change: bool = Field(
        default=True,
        description="Require the user to choose their own password at the next sign-in.",
    )
    revoke_sessions: bool = Field(default=True, description="Sign the user out of every active session.")


# ----------------------------------------------------------------------
# Read schemas
# ----------------------------------------------------------------------
class UserOrganization(BaseModel):
    """Resolved organizational placement, with names rather than bare ids."""

    model_config = ConfigDict(from_attributes=True)

    business_unit: MasterSummary | None = None
    team: MasterSummary | None = None
    designation: MasterSummary | None = None
    grade: MasterSummary | None = None
    location: MasterSummary | None = None
    employment_type: MasterSummary | None = None


class UserRead(BaseModel):
    """Full representation of a user account.

    Note the absence of ``hashed_password`` and the reset-token columns: this
    model is the boundary that keeps credentials out of API responses.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_code: str
    username: str
    first_name: str
    last_name: str
    full_name: str = Field(description="Derived from the name parts, never stored.")

    email: EmailStr
    personal_email: EmailStr | None = None
    phone_number: str | None = None
    avatar_url: str | None = None
    gender: Gender | None = None
    date_of_birth: date | None = None

    business_unit_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    grade_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    employment_type_id: uuid.UUID | None = None
    joining_date: date | None = None

    organization: UserOrganization = Field(
        description="The same references resolved to names, so list rows need no extra request."
    )

    is_active: bool
    status: RecordStatus
    is_superuser: bool
    force_password_change: bool
    is_locked: bool

    last_login_at: datetime | None = None
    password_changed_at: datetime | None = None

    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
    deleted_at: datetime | None = Field(
        default=None, description="Set when the account is archived; null when live."
    )

    @classmethod
    def from_user(cls, user: Any) -> UserRead:
        """Build the response, assembling the projected fields.

        ``status`` and ``organization`` are projections of columns the model
        already has, so they are derived here rather than duplicated in the
        database where they could fall out of step.

        Every other field is read straight off the ORM object, so adding a
        column to both the model and this schema needs no change here.
        """
        data: dict[str, Any] = {name: getattr(user, name) for name in cls.model_fields if hasattr(user, name)}
        data["status"] = RecordStatus.ACTIVE if user.is_active else RecordStatus.INACTIVE
        data["organization"] = UserOrganization.model_validate(user)
        return cls.model_validate(data)


class UserSummary(BaseModel):
    """Compact user reference for embedding in other payloads."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_code: str
    username: str
    email: EmailStr
    full_name: str
    avatar_url: str | None = None


# ----------------------------------------------------------------------
# Query parameters
# ----------------------------------------------------------------------
class UserListParams(MasterListParams):
    """Adds the user-specific filters to the shared list parameters."""

    # The shared default is `name`, which the master records have and users do
    # not -- their name is stored in two columns. Alphabetical by first name is
    # the directory ordering people expect.
    sort_by: str = Field(default="first_name", max_length=50, description="Column to sort by.")

    business_unit_id: uuid.UUID | None = Field(
        default=None, description="Return only users in this business unit."
    )
    designation_id: uuid.UUID | None = Field(
        default=None, description="Return only users with this designation."
    )
    location_id: uuid.UUID | None = Field(default=None, description="Return only users at this location.")
