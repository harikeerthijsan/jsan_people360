"""Integration tests for the Performance Management module.

The rules worth defending here are the ones a future change could quietly break:
weightage is a budget, a review is submitted once, the stages run in order, and
history is never rewritten.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.employee import Employee
from app.models.enums import EmploymentStatus
from app.models.performance import GoalProgress, PerformanceHistory
from app.models.user import User

pytestmark = pytest.mark.integration

BASE = f"{settings.API_V1_PREFIX}/performance"

TODAY = date.today()
CYCLE_START = TODAY - timedelta(days=30)
CYCLE_END = TODAY + timedelta(days=300)


def cycle_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Annual Review",
        "financial_year": "2026-27",
        "start_date": CYCLE_START.isoformat(),
        "end_date": CYCLE_END.isoformat(),
        "self_review_deadline": (CYCLE_END - timedelta(days=30)).isoformat(),
        "manager_review_deadline": (CYCLE_END - timedelta(days=20)).isoformat(),
        "hr_review_deadline": (CYCLE_END - timedelta(days=10)).isoformat(),
    }
    payload.update(overrides)
    return payload


def goal_payload(cycle_id: str, employee_id: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "cycle_id": cycle_id,
        "employee_id": employee_id,
        "title": "Ship the reporting module",
        "description": "Deliver the reporting module to production.",
        "category": "Delivery",
        "success_criteria": "Released and adopted by two clients.",
        "weightage": "40.00",
        "start_date": CYCLE_START.isoformat(),
        "due_date": (CYCLE_START + timedelta(days=120)).isoformat(),
        "priority": "high",
    }
    payload.update(overrides)
    return payload


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture
async def active_cycle(client: AsyncClient, auth_headers: dict[str, str]) -> dict[str, Any]:
    """A cycle already moved to active -- goals and reviews need one."""
    created = await client.post(f"{BASE}/cycles", json=cycle_payload(), headers=auth_headers)
    assert created.status_code == 201, created.text
    cycle = created.json()["data"]

    activated = await client.post(f"{BASE}/cycles/{cycle['id']}/status/active", headers=auth_headers)
    assert activated.status_code == 200, activated.text
    return activated.json()["data"]


@pytest.fixture
async def reviewer(db_session: AsyncSession, test_user: User) -> Employee:
    """An employee linked to the signed-in account, so it can author reviews."""
    record = Employee(
        first_name="Ravi",
        last_name="Kumar",
        official_email=f"ravi.{uuid.uuid4().hex[:8]}@jsan.example",
        joining_date=date(2024, 1, 10),
        employment_status=EmploymentStatus.ACTIVE,
        user_id=test_user.id,
    )
    db_session.add(record)
    await db_session.flush()
    return record


# ----------------------------------------------------------------------
class TestAuthentication:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/dashboard"),
            ("get", "/cycles"),
            ("post", "/cycles"),
            ("get", "/goals"),
            ("post", "/goals"),
            ("get", "/analytics"),
        ],
    )
    async def test_every_route_needs_a_token(self, client: AsyncClient, method: str, path: str) -> None:
        call = getattr(client, method)
        response = await call(f"{BASE}{path}") if method == "get" else await call(f"{BASE}{path}", json={})
        assert response.status_code == 401


class TestCycles:
    async def test_creates_a_cycle_in_draft(self, client: AsyncClient, auth_headers: dict[str, str]) -> None:
        response = await client.post(f"{BASE}/cycles", json=cycle_payload(), headers=auth_headers)

        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["status"] == "draft"
        assert data["cycle_code"].startswith("PC-")

    async def test_deadlines_must_run_in_review_order(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """HR cannot be due before the manager, who cannot be due before the employee."""
        response = await client.post(
            f"{BASE}/cycles",
            json=cycle_payload(manager_review_deadline=(CYCLE_END - timedelta(days=40)).isoformat()),
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_the_same_cycle_cannot_be_created_twice_in_a_year(
        self, client: AsyncClient, auth_headers: dict[str, str], active_cycle: dict[str, Any]
    ) -> None:
        response = await client.post(f"{BASE}/cycles", json=cycle_payload(), headers=auth_headers)

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "duplicate_cycle"

    async def test_the_same_name_is_allowed_in_a_different_year(
        self, client: AsyncClient, auth_headers: dict[str, str], active_cycle: dict[str, Any]
    ) -> None:
        """Cycles repeat annually; the name alone cannot be the identity."""
        response = await client.post(
            f"{BASE}/cycles", json=cycle_payload(financial_year="2027-28"), headers=auth_headers
        )
        assert response.status_code == 201

    async def test_a_draft_cycle_takes_no_goals(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        created = await client.post(f"{BASE}/cycles", json=cycle_payload(), headers=auth_headers)
        cycle_id = created.json()["data"]["id"]

        response = await client.post(
            f"{BASE}/goals", json=goal_payload(cycle_id, str(employee.id)), headers=auth_headers
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "cycle_not_active"


class TestGoalAssignment:
    async def test_assigns_a_goal(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        active_cycle: dict[str, Any],
        employee: Employee,
    ) -> None:
        response = await client.post(
            f"{BASE}/goals",
            json=goal_payload(active_cycle["id"], str(employee.id)),
            headers=auth_headers,
        )

        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["goal_code"].startswith("GOAL-")
        assert data["status"] == "not_started"
        assert data["completion_percentage"] == 0

    async def test_weightage_may_not_pass_one_hundred_percent(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        active_cycle: dict[str, Any],
        employee: Employee,
    ) -> None:
        """The budget is the point: over-committing makes the weighted score meaningless."""
        for index, weight in enumerate(("60.00", "30.00")):
            first = await client.post(
                f"{BASE}/goals",
                json=goal_payload(
                    active_cycle["id"], str(employee.id), weightage=weight, title=f"Goal {index}"
                ),
                headers=auth_headers,
            )
            assert first.status_code == 201, first.text

        response = await client.post(
            f"{BASE}/goals",
            json=goal_payload(active_cycle["id"], str(employee.id), weightage="20.00", title="One too many"),
            headers=auth_headers,
        )

        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "weightage_exceeded"
        # The message names what is left, so the manager can re-plan without guessing.
        assert "10" in response.json()["message"]

    async def test_a_repeated_title_is_refused(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        active_cycle: dict[str, Any],
        employee: Employee,
    ) -> None:
        payload = goal_payload(active_cycle["id"], str(employee.id), weightage="20.00")
        assert (await client.post(f"{BASE}/goals", json=payload, headers=auth_headers)).status_code == 201

        response = await client.post(f"{BASE}/goals", json=payload, headers=auth_headers)
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "duplicate_goal"

    async def test_goal_dates_must_fall_inside_the_cycle(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        active_cycle: dict[str, Any],
        employee: Employee,
    ) -> None:
        response = await client.post(
            f"{BASE}/goals",
            json=goal_payload(
                active_cycle["id"],
                str(employee.id),
                due_date=(CYCLE_END + timedelta(days=10)).isoformat(),
            ),
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert response.json()["errors"][0]["code"] == "outside_cycle"

    async def test_re_weighting_a_goal_does_not_trip_over_its_own_share(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        active_cycle: dict[str, Any],
        employee: Employee,
    ) -> None:
        """A goal already holding 60% must be allowed to move to 70%."""
        created = await client.post(
            f"{BASE}/goals",
            json=goal_payload(active_cycle["id"], str(employee.id), weightage="60.00"),
            headers=auth_headers,
        )
        goal_id = created.json()["data"]["id"]

        response = await client.patch(
            f"{BASE}/goals/{goal_id}", json={"weightage": "70.00"}, headers=auth_headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["weightage"] == "70.00"


class TestGoalProgress:
    @pytest.fixture
    async def goal(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        active_cycle: dict[str, Any],
        employee: Employee,
    ) -> dict[str, Any]:
        created = await client.post(
            f"{BASE}/goals",
            json=goal_payload(active_cycle["id"], str(employee.id), weightage="100.00"),
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text
        return created.json()["data"]

    async def test_records_progress_and_rolls_the_goal_forward(
        self, client: AsyncClient, auth_headers: dict[str, str], goal: dict[str, Any]
    ) -> None:
        response = await client.post(
            f"{BASE}/goals/{goal['id']}/progress",
            json={"completion_percentage": 45, "status": "in_progress", "comments": "Halfway"},
            headers=auth_headers,
        )

        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["completion_percentage"] == 45
        assert data["status"] == "in_progress"
        assert len(data["progress_updates"]) == 1

    async def test_progress_is_appended_never_replaced(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        goal: dict[str, Any],
        db_session: AsyncSession,
    ) -> None:
        for percent in (20, 55, 100):
            status = "completed" if percent == 100 else "in_progress"
            await client.post(
                f"{BASE}/goals/{goal['id']}/progress",
                json={"completion_percentage": percent, "status": status},
                headers=auth_headers,
            )

        rows = (
            (
                await db_session.execute(
                    select(GoalProgress).where(GoalProgress.goal_id == uuid.UUID(goal["id"]))
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 3
        assert sorted(row.completion_percentage for row in rows) == [20, 55, 100]

    async def test_a_completed_goal_must_be_at_one_hundred_percent(
        self, client: AsyncClient, auth_headers: dict[str, str], goal: dict[str, Any]
    ) -> None:
        response = await client.post(
            f"{BASE}/goals/{goal['id']}/progress",
            json={"completion_percentage": 40, "status": "completed"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_there_is_no_endpoint_that_edits_progress(
        self, client: AsyncClient, auth_headers: dict[str, str], goal: dict[str, Any]
    ) -> None:
        for method in ("patch", "put", "delete"):
            response = await getattr(client, method)(
                f"{BASE}/goals/{goal['id']}/progress", headers=auth_headers
            )
            assert response.status_code == 405


class TestReviewWorkflow:
    @pytest.fixture
    async def prepared(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        active_cycle: dict[str, Any],
        reviewer: Employee,
    ) -> dict[str, Any]:
        """One employee with one goal, ready to be reviewed."""
        created = await client.post(
            f"{BASE}/goals",
            json=goal_payload(active_cycle["id"], str(reviewer.id), weightage="100.00"),
            headers=auth_headers,
        )
        goal = created.json()["data"]
        await client.post(
            f"{BASE}/goals/{goal['id']}/progress",
            json={"completion_percentage": 100, "status": "completed"},
            headers=auth_headers,
        )
        return {"cycle": active_cycle, "employee": reviewer, "goal": goal}

    def _self_payload(self, goal_id: str) -> dict[str, Any]:
        return {
            "overall_rating": 4,
            "overall_comments": "A strong year overall.",
            "goal_ratings": [{"goal_id": goal_id, "rating": 4, "comments": "Delivered on time."}],
        }

    def _manager_payload(self, goal_id: str) -> dict[str, Any]:
        return {
            "overall_rating": 4,
            "overall_feedback": "Consistent delivery.",
            "recommendation": "promotion",
            "goal_ratings": [{"goal_id": goal_id, "rating": 5}],
        }

    async def test_the_manager_cannot_review_before_the_employee(
        self, client: AsyncClient, auth_headers: dict[str, str], prepared: dict[str, Any]
    ) -> None:
        """Reversing the order would make the self assessment a formality."""
        response = await client.post(
            f"{BASE}/reviews/{prepared['cycle']['id']}/{prepared['employee'].id}/manager",
            json=self._manager_payload(prepared["goal"]["id"]),
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "self_review_missing"

    async def test_a_partial_scorecard_is_refused(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        prepared: dict[str, Any],
    ) -> None:
        """An overall figure built from some goals cannot be compared with anyone else's."""
        response = await client.post(
            f"{BASE}/reviews/{prepared['cycle']['id']}/{prepared['employee'].id}/self",
            json={"overall_rating": 4, "overall_comments": "Good", "goal_ratings": []},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert response.json()["errors"][0]["code"] == "incomplete_ratings"

    async def test_the_full_workflow_runs_self_then_manager_then_hr(
        self, client: AsyncClient, auth_headers: dict[str, str], prepared: dict[str, Any]
    ) -> None:
        cycle_id, employee_id = prepared["cycle"]["id"], str(prepared["employee"].id)
        goal_id = prepared["goal"]["id"]

        own = await client.post(
            f"{BASE}/reviews/{cycle_id}/{employee_id}/self",
            json=self._self_payload(goal_id),
            headers=auth_headers,
        )
        assert own.status_code == 201, own.text
        assert own.json()["data"]["status"] == "submitted"

        manager = await client.post(
            f"{BASE}/reviews/{cycle_id}/{employee_id}/manager",
            json=self._manager_payload(goal_id),
            headers=auth_headers,
        )
        assert manager.status_code == 201, manager.text
        assert manager.json()["data"]["recommendation"] == "promotion"

        final = await client.post(
            f"{BASE}/reviews/{cycle_id}/{employee_id}/finalise",
            json={"final_rating": 4, "comments": "Confirmed at 4."},
            headers=auth_headers,
        )
        assert final.status_code == 201, final.text
        data = final.json()["data"]
        assert data["final_rating"] == 4
        # The two earlier stages are copied in, so a later change cannot rewrite
        # what this rating was based on.
        assert data["self_rating"] == 4
        assert data["manager_rating"] == 4
        assert data["goal_completion_percentage"] == 100

    async def test_a_submitted_review_cannot_be_submitted_again(
        self, client: AsyncClient, auth_headers: dict[str, str], prepared: dict[str, Any]
    ) -> None:
        cycle_id, employee_id = prepared["cycle"]["id"], str(prepared["employee"].id)
        payload = self._self_payload(prepared["goal"]["id"])

        assert (
            await client.post(
                f"{BASE}/reviews/{cycle_id}/{employee_id}/self", json=payload, headers=auth_headers
            )
        ).status_code == 201

        response = await client.post(
            f"{BASE}/reviews/{cycle_id}/{employee_id}/self", json=payload, headers=auth_headers
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "already_submitted"

    async def test_finalising_twice_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str], prepared: dict[str, Any]
    ) -> None:
        cycle_id, employee_id = prepared["cycle"]["id"], str(prepared["employee"].id)
        goal_id = prepared["goal"]["id"]

        await client.post(
            f"{BASE}/reviews/{cycle_id}/{employee_id}/self",
            json=self._self_payload(goal_id),
            headers=auth_headers,
        )
        await client.post(
            f"{BASE}/reviews/{cycle_id}/{employee_id}/manager",
            json=self._manager_payload(goal_id),
            headers=auth_headers,
        )
        first = await client.post(
            f"{BASE}/reviews/{cycle_id}/{employee_id}/finalise",
            json={"final_rating": 4},
            headers=auth_headers,
        )
        assert first.status_code == 201

        response = await client.post(
            f"{BASE}/reviews/{cycle_id}/{employee_id}/finalise",
            json={"final_rating": 5},
            headers=auth_headers,
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "already_finalised"

    async def test_a_rated_goal_can_no_longer_be_amended(
        self, client: AsyncClient, auth_headers: dict[str, str], prepared: dict[str, Any]
    ) -> None:
        """The rating was given against this scope; re-scoping would change its meaning."""
        cycle_id, employee_id = prepared["cycle"]["id"], str(prepared["employee"].id)
        goal_id = prepared["goal"]["id"]

        await client.post(
            f"{BASE}/reviews/{cycle_id}/{employee_id}/self",
            json=self._self_payload(goal_id),
            headers=auth_headers,
        )
        await client.post(
            f"{BASE}/reviews/{cycle_id}/{employee_id}/manager",
            json=self._manager_payload(goal_id),
            headers=auth_headers,
        )

        response = await client.patch(
            f"{BASE}/goals/{goal_id}", json={"title": "Rewritten after the fact"}, headers=auth_headers
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "goal_reviewed"

    async def test_the_rating_scale_is_enforced(
        self, client: AsyncClient, auth_headers: dict[str, str], prepared: dict[str, Any]
    ) -> None:
        response = await client.post(
            f"{BASE}/reviews/{prepared['cycle']['id']}/{prepared['employee'].id}/self",
            json={
                "overall_rating": 9,
                "overall_comments": "Off the scale",
                "goal_ratings": [{"goal_id": prepared["goal"]["id"], "rating": 4}],
            },
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestHistory:
    async def test_every_milestone_is_recorded(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        active_cycle: dict[str, Any],
        reviewer: Employee,
        db_session: AsyncSession,
    ) -> None:
        created = await client.post(
            f"{BASE}/goals",
            json=goal_payload(active_cycle["id"], str(reviewer.id), weightage="100.00"),
            headers=auth_headers,
        )
        goal_id = created.json()["data"]["id"]
        await client.post(
            f"{BASE}/goals/{goal_id}/progress",
            json={"completion_percentage": 100, "status": "completed"},
            headers=auth_headers,
        )
        await client.post(
            f"{BASE}/reviews/{active_cycle['id']}/{reviewer.id}/self",
            json={
                "overall_rating": 4,
                "overall_comments": "Done",
                "goal_ratings": [{"goal_id": goal_id, "rating": 4}],
            },
            headers=auth_headers,
        )

        rows = (
            (
                await db_session.execute(
                    select(PerformanceHistory).where(PerformanceHistory.employee_id == reviewer.id)
                )
            )
            .scalars()
            .all()
        )
        events = {row.event_type for row in rows}
        assert {"goal_assigned", "goal_completed", "self_review_submitted"} <= events

    async def test_history_is_exposed_and_read_only(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.get(f"{BASE}/history/{employee.id}", headers=auth_headers)
        assert response.status_code == 200

        for method in ("post", "patch", "delete"):
            blocked = await getattr(client, method)(f"{BASE}/history/{employee.id}", headers=auth_headers)
            assert blocked.status_code == 405


class TestRecognitionAndFeedback:
    async def test_recognises_an_employee(
        self, client: AsyncClient, auth_headers: dict[str, str], employee: Employee
    ) -> None:
        response = await client.post(
            f"{BASE}/recognitions",
            json={
                "employee_id": str(employee.id),
                "recognition_type": "star_performer",
                "title": "Outstanding delivery",
                "description": "Carried the release single-handed.",
                "awarded_on": TODAY.isoformat(),
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["data"]["recognition_type"] == "star_performer"

    async def test_feedback_records_both_sides(
        self, client: AsyncClient, auth_headers: dict[str, str], reviewer: Employee, employee: Employee
    ) -> None:
        response = await client.post(
            f"{BASE}/feedback",
            json={
                "to_employee_id": str(employee.id),
                "title": "Great handover",
                "description": "The runbook was genuinely useful.",
                "category": "appreciation",
                "visibility": "manager",
                "feedback_date": TODAY.isoformat(),
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["from_employee_id"] == str(reviewer.id)
        assert data["to_employee_id"] == str(employee.id)

    async def test_feedback_to_yourself_is_refused(
        self, client: AsyncClient, auth_headers: dict[str, str], reviewer: Employee
    ) -> None:
        response = await client.post(
            f"{BASE}/feedback",
            json={
                "to_employee_id": str(reviewer.id),
                "title": "Note to self",
                "description": "Self-congratulation.",
                "category": "appreciation",
                "feedback_date": TODAY.isoformat(),
            },
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert response.json()["errors"][0]["code"] == "self_feedback"


class TestDashboardAndAnalytics:
    async def test_the_dashboard_reports_the_headline_figures(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        active_cycle: dict[str, Any],
        employee: Employee,
    ) -> None:
        await client.post(
            f"{BASE}/goals",
            json=goal_payload(active_cycle["id"], str(employee.id), weightage="100.00"),
            headers=auth_headers,
        )

        response = await client.get(f"{BASE}/dashboard", headers=auth_headers)

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["active_cycles"] == 1
        assert data["goals_assigned"] == 1
        assert data["goals_completed"] == 0
        # One employee has goals and no self review, so one is outstanding.
        assert data["self_reviews_pending"] == 1

    async def test_the_dashboard_route_is_not_captured_by_a_cycle_id(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(f"{BASE}/dashboard", headers=auth_headers)
        assert response.status_code == 200

    async def test_analytics_returns_every_breakdown(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await client.get(f"{BASE}/analytics", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()["data"]
        assert set(data) == {
            "goal_completion",
            "business_unit_performance",
            "manager_performance",
            "rating_distribution",
            "goal_distribution",
            "performance_trend",
        }


class TestReports:
    @pytest.mark.parametrize(
        "report", ["goal-completion", "performance-summary", "employee-ratings", "recognitions"]
    )
    @pytest.mark.parametrize("fmt", ["csv", "xlsx", "pdf"])
    async def test_every_report_exports_in_every_format(
        self, client: AsyncClient, auth_headers: dict[str, str], report: str, fmt: str
    ) -> None:
        response = await client.get(
            f"{BASE}/reports/export", params={"report": report, "fmt": fmt}, headers=auth_headers
        )

        assert response.status_code == 200, response.text
        assert response.content
        assert f"{report}.{fmt}" in response.headers["content-disposition"]
