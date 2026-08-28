"""Persistence operations for :class:`app.models.app_setting.AppSetting`."""

from __future__ import annotations

from collections.abc import Sequence

from app.models.app_setting import AppSetting
from app.repositories.base import BaseRepository


class AppSettingRepository(BaseRepository[AppSetting]):
    """Queries scoped to runtime application settings."""

    model = AppSetting

    async def get_by_key(self, key: str) -> AppSetting | None:
        stmt = self._base_select().where(AppSetting.key == key)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_category(self, category: str) -> Sequence[AppSetting]:
        return await self.list(
            AppSetting.category == category,
            order_by="key",
            descending=False,
            limit=500,
        )

    async def list_public(self) -> Sequence[AppSetting]:
        """Settings safe to expose to unauthenticated clients (branding, locale)."""
        return await self.list(
            AppSetting.is_public.is_(True),
            order_by="key",
            descending=False,
            limit=500,
        )
