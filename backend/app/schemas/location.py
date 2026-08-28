"""Location request/response schemas."""

from __future__ import annotations

from pydantic import ConfigDict

from app.schemas.masters import (
    AddressText,
    CodedMasterCreateBase,
    CodedMasterReadBase,
    CodedMasterUpdateBase,
    PlaceName,
    TimezoneStr,
)


class LocationCreate(CodedMasterCreateBase):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "name": "Hyderabad HQ",
                "code": "HYD",
                "country": "India",
                "state": "Telangana",
                "city": "Hyderabad",
                "address": "Plot 12, HITEC City, Madhapur, Hyderabad 500081",
                "timezone": "Asia/Kolkata",
                "status": "active",
            }
        },
    )

    country: PlaceName
    state: PlaceName
    city: PlaceName
    address: AddressText
    timezone: TimezoneStr


class LocationUpdate(CodedMasterUpdateBase):
    country: PlaceName | None = None
    state: PlaceName | None = None
    city: PlaceName | None = None
    address: AddressText | None = None
    timezone: TimezoneStr | None = None


class LocationRead(CodedMasterReadBase):
    country: str
    state: str
    city: str
    address: str
    timezone: str
