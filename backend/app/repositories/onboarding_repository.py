import uuid

from sqlalchemy.orm import selectinload

from app.models.onboarding import (
    OnboardingCase,
    OnboardingHistory,
    OnboardingTask,
    PolicyAcknowledgement,
    PreboardingProfile,
)
from app.repositories.base import BaseRepository


class ProfileRepository(BaseRepository[PreboardingProfile]):
    model = PreboardingProfile


class CaseRepository(BaseRepository[OnboardingCase]):
    model = OnboardingCase

    async def detailed(self, case_id: uuid.UUID) -> OnboardingCase | None:
        result = await self.session.execute(
            self._base_select()
            .where(OnboardingCase.id == case_id)
            .options(selectinload(OnboardingCase.tasks))
        )
        return result.scalars().unique().one_or_none()


class TaskRepository(BaseRepository[OnboardingTask]):
    model = OnboardingTask


class PolicyRepository(BaseRepository[PolicyAcknowledgement]):
    model = PolicyAcknowledgement


class OnboardingHistoryRepository(BaseRepository[OnboardingHistory]):
    model = OnboardingHistory
