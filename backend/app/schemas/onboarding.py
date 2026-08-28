from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.schemas.employee import (
    validate_aadhaar,
    validate_account_number,
    validate_employee_pan,
    validate_ifsc,
)


class EmergencyContact(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    relationship: str = Field(min_length=2, max_length=50)
    phone_number: str = Field(min_length=7, max_length=32)
    email: EmailStr | None = None


class AddressInput(BaseModel):
    address_type: Literal["current", "permanent"]
    address_line1: str = Field(min_length=3, max_length=255)
    address_line2: str | None = Field(None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=2, max_length=20)


class BankInput(BaseModel):
    bank_name: str = Field(min_length=2, max_length=150)
    account_holder_name: str = Field(min_length=2, max_length=150)
    account_number: str
    ifsc_code: str
    branch_name: str = Field(min_length=2, max_length=150)

    @field_validator("account_number")
    @classmethod
    def account(cls, value: str) -> str:
        return validate_account_number(value)

    @field_validator("ifsc_code")
    @classmethod
    def ifsc(cls, value: str) -> str:
        return validate_ifsc(value)


class ProfileUpdate(BaseModel):
    joining_date: date
    joining_confirmed: bool
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    gender: Literal["male", "female", "non_binary", "prefer_not_to_say"]
    blood_group: Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
    marital_status: Literal["single", "married", "divorced", "widowed", "separated"]
    nationality: str = Field(min_length=2, max_length=100)
    personal_email: EmailStr
    mobile_number: str = Field(min_length=7, max_length=32)
    emergency_contact: EmergencyContact
    addresses: list[AddressInput] = Field(min_length=2, max_length=2)
    bank_details: BankInput
    aadhaar_number: str
    pan_number: str

    @field_validator("aadhaar_number")
    @classmethod
    def aadhaar(cls, value: str) -> str:
        return validate_aadhaar(value) or ""

    @field_validator("pan_number")
    @classmethod
    def pan(cls, value: str) -> str:
        return validate_employee_pan(value) or ""

    @model_validator(mode="after")
    def addresses_are_complete(self) -> Self:
        if {item.address_type for item in self.addresses} != {"current", "permanent"}:
            raise ValueError("Current and permanent addresses are required")
        return self


class ProfileStart(BaseModel):
    offer_id: uuid.UUID
    user_id: uuid.UUID


class PolicyInput(BaseModel):
    policy_code: Literal["employee_handbook", "nda", "company_policies", "code_of_conduct"]
    policy_name: str = Field(min_length=2, max_length=150)
    accepted: Literal[True]


class DocumentReview(BaseModel):
    status: Literal["approved", "rejected"]
    comments: str | None = Field(None, max_length=2000)


class ConversionInput(BaseModel):
    user_id: uuid.UUID
    official_email: EmailStr
    employment_type_id: uuid.UUID | None = None
    business_unit_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    grade_id: uuid.UUID | None = None
    work_location_id: uuid.UUID | None = None
    reporting_manager_id: uuid.UUID | None = None


class TaskCreate(BaseModel):
    category: Literal["hr", "it", "administration", "manager"]
    title: str = Field(min_length=2, max_length=200)
    owner_id: uuid.UUID
    due_date: date


class CaseCreate(BaseModel):
    tasks: list[TaskCreate] = Field(min_length=1)


class TaskUpdate(BaseModel):
    status: Literal["not_started", "in_progress", "completed", "blocked"]
    comments: str | None = Field(None, max_length=2000)


class TaskRead(TaskCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str
    comments: str | None
    completed_at: datetime | None


class CaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    profile_id: uuid.UUID
    employee_id: uuid.UUID
    status: str
    progress_percent: int
    started_at: datetime | None
    completed_at: datetime | None
    tasks: list[TaskRead]


class DashboardRead(BaseModel):
    awaiting_preboarding: int
    pending_documents: int
    pending_hr_tasks: int
    pending_it_tasks: int
    pending_manager_tasks: int
    joining_this_week: int
    delayed_joining: int
    completed_onboarding: int
