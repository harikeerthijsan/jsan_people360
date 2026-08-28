"""Grade request/response schemas."""

from __future__ import annotations

from pydantic import ConfigDict

from app.schemas.masters import (
    CodedMasterCreateBase,
    CodedMasterReadBase,
    CodedMasterUpdateBase,
    SeniorityLevel,
)


class GradeCreate(CodedMasterCreateBase):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "name": "Grade 1",
                "code": "G1",
                "level": 1,
                "description": "Entry-level individual contributor band.",
                "status": "active",
            }
        },
    )

    level: SeniorityLevel


class GradeUpdate(CodedMasterUpdateBase):
    level: SeniorityLevel | None = None


class GradeRead(CodedMasterReadBase):
    level: int
