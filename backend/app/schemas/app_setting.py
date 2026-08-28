"""Schemas for runtime application settings.

The update model carries only ``value``. The key is the row's identity, the
category and description are the platform's documentation of the setting, and
``is_editable`` is what protects system-managed values -- none of those is an
operator's to change, so none of them is in the model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

#: What a setting's value may be: whatever JSON can carry.
SettingValue = dict[str, Any] | list[Any] | str | int | float | bool | None


class AppSettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    value: SettingValue
    category: str
    description: str | None
    is_public: bool
    is_editable: bool
    updated_at: datetime


class AppSettingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: SettingValue = Field(description="The new value. JSON of any shape the setting expects.")
