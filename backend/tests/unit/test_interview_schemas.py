import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.interview import FeedbackCreate, InterviewCreate


def schedule_payload():
    start = datetime.now(UTC) + timedelta(days=1)
    return {
        "candidate_id": uuid.uuid4(),
        "interview_type": "technical",
        "interview_round": "Round 1",
        "starts_at": start,
        "ends_at": start + timedelta(hours=1),
        "time_zone": "Asia/Kolkata",
        "mode": "online",
        "meeting_link": "https://meet.example.com/1",
        "panels": [{"employee_id": uuid.uuid4(), "panel_role": "lead_interviewer"}],
    }


def test_valid_interview_schedule():
    assert InterviewCreate(**schedule_payload()).mode == "online"


def test_schedule_requires_exactly_one_lead():
    values = schedule_payload()
    values["panels"][0]["panel_role"] = "observer"
    with pytest.raises(ValidationError, match="lead interviewer"):
        InterviewCreate(**values)


def test_schedule_rejects_short_duration():
    values = schedule_payload()
    values["ends_at"] = values["starts_at"] + timedelta(minutes=5)
    with pytest.raises(ValidationError, match="duration"):
        InterviewCreate(**values)


def test_feedback_requires_all_score_categories():
    with pytest.raises(ValidationError):
        FeedbackCreate(interviewer_id=uuid.uuid4(), scores=[], overall_comments="Good", recommendation="hire")
