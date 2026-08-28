"""Designation request/response schemas."""

from __future__ import annotations

import uuid

from pydantic import ConfigDict, Field

from app.schemas.masters import (
    CodedMasterCreateBase,
    CodedMasterReadBase,
    CodedMasterUpdateBase,
    MasterListParams,
    MasterSummary,
    SeniorityLevel,
)


class DesignationCreate(CodedMasterCreateBase):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "name": "Senior Software Engineer",
                "code": "SSE",
                "business_unit_id": "0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f",
                "level": 3,
                "description": "Delivers complex features and mentors engineers.",
                "status": "active",
            }
        },
    )

    business_unit_id: uuid.UUID = Field(description="Owning business unit.")
    level: SeniorityLevel


class DesignationUpdate(CodedMasterUpdateBase):
    business_unit_id: uuid.UUID | None = Field(
        default=None, description="Move the designation to a different business unit."
    )
    level: SeniorityLevel | None = None


class DesignationRead(CodedMasterReadBase):
    business_unit_id: uuid.UUID
    business_unit: MasterSummary
    level: int


class DesignationListParams(MasterListParams):
    business_unit_id: uuid.UUID | None = Field(
        default=None, description="Return only designations in this business unit."
    )
    level: int | None = Field(default=None, ge=1, le=99, description="Return only this seniority level.")
