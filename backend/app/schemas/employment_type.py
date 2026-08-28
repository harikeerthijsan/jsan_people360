"""Employment type request/response schemas."""

from __future__ import annotations

from pydantic import ConfigDict

from app.schemas.masters import (
    CodedMasterCreateBase,
    CodedMasterReadBase,
    CodedMasterUpdateBase,
)


class EmploymentTypeCreate(CodedMasterCreateBase):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "name": "Full Time",
                "code": "FULL_TIME",
                "description": "Permanent employee on the company payroll.",
                "status": "active",
            }
        },
    )


class EmploymentTypeUpdate(CodedMasterUpdateBase):
    pass


class EmploymentTypeRead(CodedMasterReadBase):
    pass
