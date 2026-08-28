"""Shared response and pagination schemas.

Every endpoint in the platform returns the same envelope::

    {
      "success": true,
      "message": "Operation completed successfully",
      "data": {},
      "errors": null
    }
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

DEFAULT_SUCCESS_MESSAGE = "Operation completed successfully"


class ErrorDetail(BaseModel):
    """A single, user-presentable error entry."""

    model_config = ConfigDict(populate_by_name=True)

    code: str = Field(description="Machine readable error code.")
    message: str = Field(description="Human readable description of the problem.")
    field: str | None = Field(
        default=None, description="Dotted path of the offending field, when applicable."
    )


class APIResponse(BaseModel, Generic[T]):
    """Standard success envelope returned by every endpoint."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": DEFAULT_SUCCESS_MESSAGE,
                "data": {},
                "errors": None,
            }
        }
    )

    success: bool = True
    message: str = DEFAULT_SUCCESS_MESSAGE
    data: T | None = None
    errors: list[ErrorDetail] | None = None

    @classmethod
    def ok(cls, data: T | None = None, message: str = DEFAULT_SUCCESS_MESSAGE) -> APIResponse[T]:
        return cls(success=True, message=message, data=data, errors=None)


class APIErrorResponse(BaseModel):
    """Standard failure envelope. Documented so OpenAPI shows real error shapes."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "message": "One or more fields failed validation.",
                "data": None,
                "errors": [
                    {
                        "code": "validation_error",
                        "message": "value is not a valid email address",
                        "field": "email",
                    }
                ],
            }
        }
    )

    success: bool = False
    message: str
    data: Any | None = None
    errors: list[ErrorDetail] | None = None


class PageMeta(BaseModel):
    """Pagination metadata attached to list responses."""

    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    has_next: bool
    has_previous: bool


class Page(BaseModel, Generic[T]):
    """Envelope payload for paginated collections."""

    items: list[T]
    meta: PageMeta

    @classmethod
    def create(cls, items: list[T], *, page: int, page_size: int, total_items: int) -> Page[T]:
        total_pages = (total_items + page_size - 1) // page_size if page_size else 0
        return cls(
            items=items,
            meta=PageMeta(
                page=page,
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )


class PaginationParams(BaseModel):
    """Reusable query parameters for paginated endpoints."""

    page: int = Field(default=1, ge=1, description="1-based page number.")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page.")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class MessageData(BaseModel):
    """Payload for endpoints that only need to acknowledge an action."""

    detail: str
