"""Organization (company profile) request/response schemas."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, AnyHttpUrl, ConfigDict, Field, field_validator

from app.schemas.masters import (
    CurrencyStr,
    MasterCreateBase,
    MasterReadBase,
    MasterUpdateBase,
    PlaceName,
    TimezoneStr,
    normalise_name,
    normalise_optional_text,
    validate_gstin,
    validate_pan,
)

LegalName = Annotated[str, Field(min_length=2, max_length=250), AfterValidator(normalise_name)]
RegistrationNumber = Annotated[str, Field(min_length=2, max_length=100), AfterValidator(normalise_name)]
GstNumber = Annotated[
    str | None,
    Field(default=None, max_length=15, description="Optional 15-character GSTIN."),
    AfterValidator(validate_gstin),
]
PanNumber = Annotated[
    str | None,
    Field(default=None, max_length=10, description="Optional 10-character PAN."),
    AfterValidator(validate_pan),
]
AddressLine = Annotated[str, Field(min_length=3, max_length=255)]
PostalCode = Annotated[
    str | None, Field(default=None, max_length=20), AfterValidator(normalise_optional_text)
]


def _url_to_str(value: AnyHttpUrl | None) -> str | None:
    """Validate as a URL, persist as a plain string.

    ``AnyHttpUrl`` gives real validation; the column is a ``VARCHAR``, so the
    value is converted back before it reaches the model.
    """
    return str(value) if value is not None else None


WebsiteUrl = Annotated[AnyHttpUrl | None, Field(default=None), AfterValidator(_url_to_str)]
LogoUrl = Annotated[AnyHttpUrl | None, Field(default=None), AfterValidator(_url_to_str)]


class OrganizationCreate(MasterCreateBase):
    """``name`` is the trading/company name; ``legal_name`` is the registered one."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "name": "JSAN Technologies",
                "legal_name": "JSAN Technologies Private Limited",
                "registration_number": "U72900TG2015PTC098765",
                "gst_number": "36AABCJ1234M1ZP",
                "pan_number": "AABCJ1234M",
                "website": "https://www.jsan.example",
                "logo_url": None,
                "timezone": "Asia/Kolkata",
                "currency": "INR",
                "address_line1": "Plot 12, HITEC City",
                "address_line2": "Madhapur",
                "city": "Hyderabad",
                "state": "Telangana",
                "country": "India",
                "postal_code": "500081",
                "status": "active",
            }
        },
    )

    legal_name: LegalName
    registration_number: RegistrationNumber
    gst_number: GstNumber = None
    pan_number: PanNumber = None

    logo_url: LogoUrl = None
    website: WebsiteUrl = None

    timezone: TimezoneStr
    currency: CurrencyStr

    address_line1: AddressLine
    address_line2: str | None = Field(default=None, max_length=255)
    city: PlaceName
    state: PlaceName
    country: PlaceName
    postal_code: PostalCode = None

    @field_validator("address_line2")
    @classmethod
    def _clean_address_line2(cls, value: str | None) -> str | None:
        return normalise_optional_text(value)


class OrganizationUpdate(MasterUpdateBase):
    legal_name: LegalName | None = None
    registration_number: RegistrationNumber | None = None
    gst_number: GstNumber = None
    pan_number: PanNumber = None

    logo_url: LogoUrl = None
    website: WebsiteUrl = None

    timezone: TimezoneStr | None = None
    currency: CurrencyStr | None = None

    address_line1: AddressLine | None = None
    address_line2: str | None = Field(default=None, max_length=255)
    city: PlaceName | None = None
    state: PlaceName | None = None
    country: PlaceName | None = None
    postal_code: PostalCode = None

    @field_validator("address_line2")
    @classmethod
    def _clean_address_line2(cls, value: str | None) -> str | None:
        return normalise_optional_text(value)


class OrganizationRead(MasterReadBase):
    legal_name: str
    registration_number: str
    gst_number: str | None = None
    pan_number: str | None = None

    logo_url: str | None = None
    website: str | None = None

    timezone: str
    currency: str

    address_line1: str
    address_line2: str | None = None
    city: str
    state: str
    country: str
    postal_code: str | None = None
