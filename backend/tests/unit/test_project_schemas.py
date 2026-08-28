import uuid
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.project import AllocationCreate, ProjectCreate


def test_allocation_percentage_cannot_exceed_one_hundred():
    with pytest.raises(ValidationError):
        AllocationCreate(
            employee_id=uuid.uuid4(),
            role="Engineer",
            allocation_percentage=101,
            start_date=date.today(),
            billable=True,
            reason="Delivery assignment",
        )


def test_allocation_rejects_inverted_dates():
    with pytest.raises(ValidationError, match="end date"):
        AllocationCreate(
            employee_id=uuid.uuid4(),
            role="Engineer",
            allocation_percentage=50,
            start_date=date.today(),
            end_date=date.today() - timedelta(days=1),
            billable=True,
            reason="Delivery assignment",
        )


def test_project_requires_manager_and_valid_dates():
    with pytest.raises(ValidationError):
        ProjectCreate(
            project_name="Platform",
            client_id=uuid.uuid4(),
            description="Delivery project",
            start_date=date.today(),
            end_date=date.today() - timedelta(days=1),
            project_manager_id=uuid.uuid4(),
        )
