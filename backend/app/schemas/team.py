"""Team request/response schemas."""

from __future__ import annotations

import uuid

from pydantic import ConfigDict, Field

from app.schemas.masters import (
    MasterCreateBase,
    MasterListParams,
    MasterReadBase,
    MasterSummary,
    MasterUpdateBase,
)
from app.schemas.user import UserSummary


class TeamCreate(MasterCreateBase):
    """Teams carry no code -- see :class:`app.models.team.Team`."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={
            "example": {
                "name": "Platform Engineering",
                "business_unit_id": "0f9c1d2e-3a4b-5c6d-7e8f-9a0b1c2d3e4f",
                "manager_id": None,
                "description": "Owns the shared services every product team builds on.",
                "status": "active",
            }
        },
    )

    business_unit_id: uuid.UUID = Field(description="Owning business unit.")
    manager_id: uuid.UUID | None = Field(
        default=None,
        description="Team manager. References a user until the Employee module exists.",
    )


class TeamUpdate(MasterUpdateBase):
    business_unit_id: uuid.UUID | None = Field(
        default=None, description="Move the team to a different business unit."
    )
    manager_id: uuid.UUID | None = Field(default=None, description="Reassign the manager.")


class TeamRead(MasterReadBase):
    business_unit_id: uuid.UUID
    business_unit: MasterSummary
    manager_id: uuid.UUID | None = None
    manager: UserSummary | None = None


class TeamListParams(MasterListParams):
    business_unit_id: uuid.UUID | None = Field(
        default=None, description="Return only teams in this business unit."
    )
    manager_id: uuid.UUID | None = Field(default=None, description="Return only teams managed by this user.")
