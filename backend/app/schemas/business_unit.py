"""Business unit request/response schemas."""

from __future__ import annotations

from pydantic import ConfigDict

from app.schemas.masters import (
    CodedMasterCreateBase,
    CodedMasterReadBase,
    CodedMasterUpdateBase,
)


class BusinessUnitCreate(CodedMasterCreateBase):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "name": "Technology Services",
                "code": "TECH",
                "description": "Delivery organisation for all client engineering work.",
                "status": "active",
            }
        },
    )


class BusinessUnitUpdate(CodedMasterUpdateBase):
    pass


class BusinessUnitRead(CodedMasterReadBase):
    pass
