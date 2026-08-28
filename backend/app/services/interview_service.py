from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from openpyxl import Workbook
from sqlalchemy import func, select

from app.core.exceptions import ConflictError, NotFoundError
from app.models.employee import Employee
from app.models.interview import (
    Interview,
    InterviewAttachment,
    InterviewFeedback,
    InterviewPanel,
    InterviewScheduleHistory,
    InterviewScore,
)
from app.models.recruitment import Candidate, CandidateStageHistory, RecruitmentStage
from app.models.requisition import Notification
from app.repositories.interview_repository import (
    FeedbackRepository,
    InterviewAttachmentRepository,
    InterviewRepository,
    PanelRepository,
    ScheduleHistoryRepository,
    ScoreRepository,
)
from app.repositories.requisition_repository import NotificationRepository
from app.schemas.interview import (
    AttachmentLink,
    DecisionRequest,
    FeedbackCreate,
    InterviewCreate,
    InterviewDashboard,
    InterviewListParams,
    InterviewUpdate,
    PanelAssign,
    RescheduleRequest,
)
from app.services.audit_service import AuditService
from app.utils.datetime import utc_now


class InterviewService:
    def __init__(
        self,
        interviews: InterviewRepository,
        panels: PanelRepository,
        feedback: FeedbackRepository,
        scores: ScoreRepository,
        history: ScheduleHistoryRepository,
        attachments: InterviewAttachmentRepository,
        notifications: NotificationRepository,
        audit: AuditService,
    ) -> None:
        self.interviews: InterviewRepository = interviews
        self.panels: PanelRepository = panels
        self.feedback: FeedbackRepository = feedback
        self.scores: ScoreRepository = scores
        self.history: ScheduleHistoryRepository = history
        self.attachments: InterviewAttachmentRepository = attachments
        self.notifications: NotificationRepository = notifications
        self.audit: AuditService = audit

    async def get(self, interview_id: uuid.UUID) -> Interview:
        item = await self.interviews.get_detailed(interview_id)
        if not item:
            raise NotFoundError("Interview")
        return item

    async def list(self, params: InterviewListParams) -> tuple[Sequence[Interview], int]:
        return await self.interviews.search(params)

    async def schedule(self, payload: InterviewCreate, actor: uuid.UUID) -> Interview:
        candidate = await self.interviews.session.get(Candidate, payload.candidate_id)
        if not candidate or candidate.deleted_at:
            raise NotFoundError("Candidate")
        if payload.starts_at <= datetime.now(UTC):
            raise ConflictError("Interview must be scheduled in the future.")
        employee_ids = [x.employee_id for x in payload.panels]
        if not await self.interviews.employees_exist(employee_ids):
            raise NotFoundError("Panel employee")
        await self._check_conflicts(candidate.id, employee_ids, payload.starts_at, payload.ends_at)
        values = payload.model_dump(exclude={"panels"})
        if values.get("meeting_link"):
            values["meeting_link"] = str(values["meeting_link"])
        item = await self.interviews.add(
            Interview(**values, job_opening_id=candidate.job_opening_id), actor_id=actor
        )
        for panel in payload.panels:
            await self.panels.add(InterviewPanel(interview_id=item.id, **panel.model_dump()), actor_id=actor)
            await self._notify_employee(
                panel.employee_id,
                "Interview scheduled",
                f"{item.interview_code} has been assigned to you",
                item,
                actor,
            )
        await self._history(item, "scheduled", None, None, item.starts_at, item.ends_at, actor)
        await self._audit("interview.scheduled", item.id, actor)
        return await self.get(item.id)

    async def update(self, interview_id: uuid.UUID, payload: InterviewUpdate, actor: uuid.UUID) -> Interview:
        item = await self.get(interview_id)
        if item.status in {"completed", "cancelled"}:
            raise ConflictError("Completed or cancelled interviews cannot be edited.")
        values = payload.model_dump(exclude_unset=True)
        if values.get("meeting_link"):
            values["meeting_link"] = str(values["meeting_link"])
        await self.interviews.update(item, values, actor_id=actor)
        await self._history(item, "updated", None, None, item.starts_at, item.ends_at, actor)
        await self._audit("interview.updated", item.id, actor)
        return item

    async def reschedule(
        self, interview_id: uuid.UUID, payload: RescheduleRequest, actor: uuid.UUID
    ) -> Interview:
        item = await self.get(interview_id)
        if item.status in {"completed", "cancelled"}:
            raise ConflictError("This interview cannot be rescheduled.")
        if payload.starts_at <= datetime.now(UTC):
            raise ConflictError("Interview must be rescheduled to a future time.")
        employee_ids = [x.employee_id for x in item.panels]
        await self._check_conflicts(
            item.candidate_id, employee_ids, payload.starts_at, payload.ends_at, item.id
        )
        old_start, old_end = item.starts_at, item.ends_at
        await self.interviews.update(
            item,
            {
                "starts_at": payload.starts_at,
                "ends_at": payload.ends_at,
                "time_zone": payload.time_zone,
                "status": "rescheduled",
            },
            actor_id=actor,
        )
        await self._history(
            item,
            "rescheduled",
            old_start,
            old_end,
            payload.starts_at,
            payload.ends_at,
            actor,
            payload.comments,
        )
        for panel in item.panels:
            await self._notify_employee(
                panel.employee_id,
                "Interview rescheduled",
                f"{item.interview_code} schedule changed",
                item,
                actor,
            )
        await self._audit("interview.rescheduled", item.id, actor)
        return item

    async def cancel(self, interview_id: uuid.UUID, comments: str | None, actor: uuid.UUID) -> Interview:
        item = await self.get(interview_id)
        if item.status in {"completed", "cancelled"}:
            raise ConflictError("This interview cannot be cancelled.")
        await self.interviews.update(item, {"status": "cancelled"}, actor_id=actor)
        await self._history(item, "cancelled", item.starts_at, item.ends_at, None, None, actor, comments)
        for panel in item.panels:
            await self._notify_employee(
                panel.employee_id, "Interview cancelled", item.interview_code, item, actor
            )
        await self._audit("interview.cancelled", item.id, actor)
        return item

    async def replace_panel(
        self, interview_id: uuid.UUID, panel_items: Sequence[PanelAssign], actor: uuid.UUID
    ) -> Interview:
        item = await self.get(interview_id)
        employee_ids = [x.employee_id for x in panel_items]
        if not employee_ids:
            raise ConflictError("At least one panel member is required.")
        if len(employee_ids) != len(set(employee_ids)):
            raise ConflictError("An interviewer cannot appear twice on the panel.")
        if sum(x.panel_role == "lead_interviewer" for x in panel_items) != 1:
            raise ConflictError("Exactly one lead interviewer is required.")
        if not await self.interviews.employees_exist(employee_ids):
            raise NotFoundError("Panel employee")
        await self._check_conflicts(item.candidate_id, employee_ids, item.starts_at, item.ends_at, item.id)
        for existing in item.panels:
            await self.panels.soft_delete(existing, actor_id=actor)
        for panel in panel_items:
            await self.panels.add(InterviewPanel(interview_id=item.id, **panel.model_dump()), actor_id=actor)
        await self._history(item, "panel_changed", None, None, item.starts_at, item.ends_at, actor)
        await self._audit("interview.panel_changed", item.id, actor)
        return await self.get(item.id)

    async def submit_feedback(
        self, interview_id: uuid.UUID, payload: FeedbackCreate, actor: uuid.UUID
    ) -> Interview:
        item = await self.get(interview_id)
        panel = next(
            (x for x in item.panels if x.employee_id == payload.interviewer_id and x.deleted_at is None), None
        )
        if not panel:
            raise ConflictError("Feedback can only be submitted by an assigned interviewer.")
        if panel.panel_role == "observer":
            raise ConflictError("Observers do not submit scorecards.")
        if await self.feedback.get_by(interview_id=item.id, interviewer_id=payload.interviewer_id):
            raise ConflictError("This interviewer has already submitted feedback.")
        feedback = await self.feedback.add(
            InterviewFeedback(
                interview_id=item.id,
                interviewer_id=payload.interviewer_id,
                overall_comments=payload.overall_comments,
                recommendation=payload.recommendation,
            ),
            actor_id=actor,
        )
        for value in payload.scores:
            await self.scores.add(
                InterviewScore(feedback_id=feedback.id, **value.model_dump()), actor_id=actor
            )
        await self.panels.update(panel, {"status": "feedback_submitted"}, actor_id=actor)
        await self._calculate(item, actor)
        candidate = await self.interviews.session.get(Candidate, item.candidate_id)
        if candidate and candidate.recruiter_id:
            await self._notify(
                candidate.recruiter_id, "Interview feedback submitted", item.interview_code, item, actor
            )
        await self._history(item, "feedback_submitted", None, None, item.starts_at, item.ends_at, actor)
        await self._audit("interview.feedback_submitted", item.id, actor)
        return await self.get(item.id)

    async def decision(
        self, interview_id: uuid.UUID, payload: DecisionRequest, actor: uuid.UUID
    ) -> Interview:
        item = await self.get(interview_id)
        if not item.feedback:
            raise ConflictError("At least one scorecard is required before a decision.")
        candidate = await self.interviews.session.get(Candidate, item.candidate_id)
        if candidate is None:
            raise NotFoundError("Candidate")
        stage = None
        if payload.target_stage_id:
            stage = await self.interviews.session.get(RecruitmentStage, payload.target_stage_id)
        else:
            default_name = {
                "reject": "Rejected",
                "hold": "Screening",
                "shortlist": "Selected",
                "final_selection": "Selected",
            }.get(payload.decision)
            if default_name:
                stage = await self.interviews.session.scalar(
                    select(RecruitmentStage).where(
                        RecruitmentStage.name == default_name, RecruitmentStage.deleted_at.is_(None)
                    )
                )
        if payload.decision == "next_round" and not stage:
            raise ConflictError("Next round requires a target recruitment stage.")
        if stage:
            old_stage = candidate.stage_id
            candidate.stage_id = stage.id
            await self.interviews.session.flush()
            self.interviews.session.add(
                CandidateStageHistory(
                    candidate_id=candidate.id,
                    from_stage_id=old_stage,
                    to_stage_id=stage.id,
                    comments=payload.comments,
                    created_by=actor,
                    updated_by=actor,
                )
            )
        await self.interviews.update(
            item, {"decision": payload.decision, "status": "completed"}, actor_id=actor
        )
        await self._history(
            item, "decision_taken", None, None, item.starts_at, item.ends_at, actor, payload.comments
        )
        if candidate.recruiter_id:
            await self._notify(
                candidate.recruiter_id,
                "Interview decision recorded",
                f"{item.interview_code}: {payload.decision}",
                item,
                actor,
            )
        await self._audit("interview.decision_taken", item.id, actor)
        return item

    async def attach(
        self, interview_id: uuid.UUID, payload: AttachmentLink, actor: uuid.UUID
    ) -> InterviewAttachment:
        item = await self.get(interview_id)
        if not await self.attachments.document_exists(payload.document_id):
            raise NotFoundError("Document")
        result = await self.attachments.add(
            InterviewAttachment(interview_id=item.id, **payload.model_dump()), actor_id=actor
        )
        await self._audit("interview.attachment_added", item.id, actor)
        return result

    async def dashboard(self) -> InterviewDashboard:
        s = self.interviews.session
        now = utc_now()
        today = now.date()

        async def count(*criteria: Any) -> int:
            return int(
                await s.scalar(
                    select(func.count())
                    .select_from(Interview)
                    .where(Interview.deleted_at.is_(None), *criteria)
                )
                or 0
            )

        total = await count()
        completed = await count(Interview.status == "completed")
        pending = await s.scalar(
            select(func.count())
            .select_from(InterviewPanel)
            .join(Interview)
            .where(
                InterviewPanel.deleted_at.is_(None),
                Interview.deleted_at.is_(None),
                Interview.status.in_(["scheduled", "rescheduled"]),
                InterviewPanel.panel_role != "observer",
                InterviewPanel.status != "feedback_submitted",
            )
        )
        by_status = (
            await s.execute(
                select(Interview.status, func.count())
                .where(Interview.deleted_at.is_(None))
                .group_by(Interview.status)
            )
        ).all()
        workload = (
            await s.execute(
                select(InterviewPanel.employee_id, func.count())
                .join(Interview)
                .where(
                    InterviewPanel.deleted_at.is_(None),
                    Interview.deleted_at.is_(None),
                    Interview.status.in_(["scheduled", "rescheduled"]),
                )
                .group_by(InterviewPanel.employee_id)
            )
        ).all()
        average = await s.scalar(
            select(func.avg(Interview.overall_score)).where(
                Interview.deleted_at.is_(None), Interview.overall_score.is_not(None)
            )
        )
        selected = await count(Interview.decision.in_(["shortlist", "final_selection", "next_round"]))
        return InterviewDashboard(
            todays_interviews=await count(func.date(Interview.starts_at) == today),
            upcoming_interviews=await count(
                Interview.starts_at > now, Interview.status.in_(["scheduled", "rescheduled"])
            ),
            completed_interviews=completed,
            cancelled_interviews=await count(Interview.status == "cancelled"),
            pending_feedback=int(pending or 0),
            average_score=round(float(average or 0), 2),
            selection_ratio=round(selected / completed * 100, 2) if completed else 0,
            completion_rate=round(completed / total * 100, 2) if total else 0,
            candidate_status=[{"label": str(k), "count": int(v)} for k, v in by_status],
            interviewer_workload=[{"label": str(k), "count": int(v)} for k, v in workload],
        )

    async def export(self, params: InterviewListParams, fmt: str) -> tuple[bytes, str]:
        rows, _ = await self.list(params.model_copy(update={"page": 1, "page_size": 100}))
        headers = ["Interview", "Candidate", "Round", "Type", "Start", "Status", "Score", "Decision"]
        data = [
            [
                x.interview_code,
                str(x.candidate_id),
                x.interview_round,
                x.interview_type,
                x.starts_at.isoformat(),
                x.status,
                x.overall_score,
                x.decision,
            ]
            for x in rows
        ]
        if fmt == "csv":
            text = io.StringIO()
            writer = csv.writer(text)
            writer.writerow(headers)
            writer.writerows(data)
            return text.getvalue().encode(), "text/csv"
        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        for row in data:
            ws.append(row)
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    async def _check_conflicts(
        self,
        candidate_id: uuid.UUID,
        employee_ids: Sequence[uuid.UUID],
        starts_at: datetime,
        ends_at: datetime,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        if await self.interviews.candidate_conflict(candidate_id, starts_at, ends_at, exclude_id):
            raise ConflictError(
                "Candidate already has an overlapping interview.", error_code="candidate_conflict"
            )
        conflicts = await self.interviews.panel_conflicts(employee_ids, starts_at, ends_at, exclude_id)
        if conflicts:
            raise ConflictError(
                f"Interviewers are already booked: {', '.join(map(str, conflicts))}",
                error_code="interviewer_conflict",
            )

    async def _calculate(self, item: Interview, actor: uuid.UUID) -> None:
        await self.interviews.session.flush()
        values = (
            (
                await self.interviews.session.execute(
                    select(InterviewScore.score)
                    .join(InterviewFeedback)
                    .where(
                        InterviewFeedback.interview_id == item.id,
                        InterviewFeedback.deleted_at.is_(None),
                        InterviewScore.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        recommendations = (
            (
                await self.interviews.session.execute(
                    select(InterviewFeedback.recommendation).where(
                        InterviewFeedback.interview_id == item.id, InterviewFeedback.deleted_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        rank = {"reject": 0, "hold": 1, "hire": 2, "strong_hire": 3}
        recommendation = max(recommendations, key=lambda x: (recommendations.count(x), rank[x]))
        required = [x for x in item.panels if x.panel_role != "observer" and x.deleted_at is None]
        submitted = await self.feedback.count(InterviewFeedback.interview_id == item.id)
        await self.interviews.update(
            item,
            {
                "overall_score": round(sum(values) / len(values), 2),
                "overall_recommendation": recommendation,
                "status": "feedback_completed" if submitted >= len(required) else item.status,
            },
            actor_id=actor,
        )

    async def _history(
        self,
        item: Interview,
        action: str,
        old_start: datetime | None,
        old_end: datetime | None,
        new_start: datetime | None,
        new_end: datetime | None,
        actor: uuid.UUID,
        comments: str | None = None,
    ) -> None:
        await self.history.add(
            InterviewScheduleHistory(
                interview_id=item.id,
                action=action,
                previous_starts_at=old_start,
                previous_ends_at=old_end,
                new_starts_at=new_start,
                new_ends_at=new_end,
                comments=comments,
            ),
            actor_id=actor,
        )

    async def _notify_employee(
        self,
        employee_id: uuid.UUID,
        title: str,
        message: str,
        item: Interview,
        actor: uuid.UUID,
    ) -> None:
        employee = await self.interviews.session.get(Employee, employee_id)
        if employee and employee.user_id:
            await self._notify(employee.user_id, title, message, item, actor)

    async def _notify(
        self,
        user_id: uuid.UUID,
        title: str,
        message: str,
        item: Interview,
        actor: uuid.UUID,
    ) -> None:
        await self.notifications.add(
            Notification(
                user_id=user_id,
                title=title,
                message=message,
                link=f"/interviews/{item.id}",
                notification_type="interview",
            ),
            actor_id=actor,
        )

    async def _audit(self, action: str, entity_id: uuid.UUID, actor: uuid.UUID) -> None:
        await self.audit.record_success(action, actor_id=actor, entity_type="interview", entity_id=entity_id)
