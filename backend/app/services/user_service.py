"""User account business logic.

Covers both audiences the module serves: administrators managing the directory,
and users managing their own profile. They are separate methods taking separate
schemas, because "what an admin may change" and "what you may change about
yourself" are different questions with different answers.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.audit_log import AuditAction
from app.models.enums import RecordStatus
from app.models.user import User
from app.repositories.organization_repository import TeamRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    AdminPasswordReset,
    ProfileUpdate,
    UserCreate,
    UserListParams,
    UserUpdate,
)
from app.services.audit_service import AuditService
from app.services.token_service import TokenService
from app.utils.datetime import utc_now
from app.utils.strings import mask_email

logger = get_logger("services.user")


class UserService:
    """Create and maintain user accounts."""

    def __init__(
        self,
        repository: UserRepository,
        audit_service: AuditService,
        team_repository: TeamRepository | None = None,
        token_service: TokenService | None = None,
    ) -> None:
        self._users = repository
        self._audit = audit_service
        # Optional so the authentication flow, which only needs `set_password`,
        # is not forced to construct the whole directory dependency graph.
        self._teams = team_repository
        self._tokens = token_service

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    async def list(self, params: UserListParams) -> tuple[Sequence[User], int]:
        if params.sort_by not in self._users.sortable_fields:
            allowed = ", ".join(sorted(self._users.sortable_fields))
            raise BadRequestError(
                f"Cannot sort by {params.sort_by!r}. Sortable columns are: {allowed}.",
                error_code="invalid_sort_field",
            )
        return await self._users.list_page(params)

    async def get_by_id(self, user_id: uuid.UUID, *, include_archived: bool = True) -> User:
        """Fetch one account, or raise :class:`NotFoundError`.

        Archived accounts are readable so a link from the archive list, or a
        stale bookmark, resolves rather than returning a confusing 404.
        """
        user = await self._users.get(user_id, include_deleted=include_archived)
        if user is None:
            raise NotFoundError("User")
        return user

    async def get_by_email(self, email: str) -> User | None:
        return await self._users.get_by_email(email)

    # ------------------------------------------------------------------
    # Administrator writes
    # ------------------------------------------------------------------
    async def create(self, payload: UserCreate, *, actor_id: uuid.UUID | None = None) -> User:
        """Provision a new account.

        ``user_code`` is not set here: the database generates it from a sequence,
        which is the only way two concurrent creates cannot be handed the same
        number.
        """
        data = payload.model_dump()
        password = data.pop("password")
        status = data.pop("status")

        await self._assert_identifiers_available(data["email"], data["username"], exclude_id=None)
        await self._assert_org_references_usable(data)

        user = User(
            **data,
            is_active=status is RecordStatus.ACTIVE,
            hashed_password=hash_password(password),
            password_changed_at=utc_now(),
        )
        await self._users.add(user, actor_id=actor_id)
        created = await self._reload(user.id)

        await self._audit.record_success(
            AuditAction.USER_CREATED,
            actor_id=actor_id,
            entity_type="user",
            entity_id=created.id,
            description=f"Created account {created.user_code} for {mask_email(created.email)}",
            context={"user_code": created.user_code, "username": created.username},
        )
        logger.info("User created", extra={"user_id": str(created.id), "user_code": created.user_code})
        return created

    async def update(
        self, user_id: uuid.UUID, payload: UserUpdate, *, actor_id: uuid.UUID | None = None
    ) -> User:
        """Apply an administrator's partial update."""
        user = await self.get_by_id(user_id)
        self._assert_not_archived(user)

        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return user

        status = changes.pop("status", None)
        if status is not None:
            changes["is_active"] = status is RecordStatus.ACTIVE
            if not changes["is_active"]:
                await self._assert_may_disable(user, actor_id, verb="deactivate")

        # Uniqueness is evaluated against the resulting record, so a partial
        # update cannot sidestep it.
        await self._assert_identifiers_available(
            changes.get("email", user.email),
            changes.get("username", user.username),
            exclude_id=user.id,
        )
        await self._assert_org_references_usable(changes)

        await self._users.update(user, changes, actor_id=actor_id)
        updated = await self._reload(user.id)

        await self._audit.record_success(
            AuditAction.USER_UPDATED,
            actor_id=actor_id,
            entity_type="user",
            entity_id=updated.id,
            description=f"Updated account {updated.user_code}",
            context={"fields": sorted(changes)},
        )
        return updated

    async def set_status(
        self, user_id: uuid.UUID, *, active: bool, actor_id: uuid.UUID | None = None
    ) -> User:
        """Activate or deactivate an account."""
        user = await self.get_by_id(user_id)
        self._assert_not_archived(user)

        if user.is_active == active:
            state = "active" if active else "inactive"
            raise ConflictError(f"This account is already {state}.", error_code=f"already_{state}")

        if not active:
            await self._assert_may_disable(user, actor_id, verb="deactivate")

        await self._users.update(user, {"is_active": active}, actor_id=actor_id)
        if not active and self._tokens is not None:
            # A deactivated account must lose its live sessions immediately;
            # otherwise the existing access token keeps working until it expires.
            await self._tokens.revoke_all_for_user(user.id, reason="account_deactivated")

        await self._audit.record_success(
            AuditAction.USER_ACTIVATED if active else AuditAction.USER_DEACTIVATED,
            actor_id=actor_id,
            entity_type="user",
            entity_id=user.id,
            description=f"{'Activated' if active else 'Deactivated'} account {user.user_code}",
        )
        return await self._reload(user.id)

    async def archive(self, user_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> User:
        """Soft delete an account, after checking nothing still depends on it."""
        user = await self.get_by_id(user_id)

        if user.deleted_at is not None:
            raise ConflictError("This account is already archived.", error_code="already_archived")

        await self._assert_may_disable(user, actor_id, verb="archive")
        await self._assert_no_linked_records(user)

        await self._users.soft_delete(user, actor_id=actor_id)
        if self._tokens is not None:
            await self._tokens.revoke_all_for_user(user.id, reason="account_archived")

        await self._audit.record_success(
            AuditAction.USER_ARCHIVED,
            actor_id=actor_id,
            entity_type="user",
            entity_id=user.id,
            description=f"Archived account {user.user_code}",
        )
        logger.info("User archived", extra={"user_id": str(user.id)})
        return await self._reload(user.id)

    async def restore(self, user_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> User:
        """Bring an archived account back into use."""
        user = await self.get_by_id(user_id)

        if user.deleted_at is None:
            raise ConflictError("This account is not archived.", error_code="not_archived")

        # The address and username were still reserved while archived, but
        # another account could have taken them if this one was archived, the
        # value reused, and a restore attempted afterwards.
        await self._assert_identifiers_available(user.email, user.username, exclude_id=user.id)

        await self._users.restore(user, actor_id=actor_id)
        await self._audit.record_success(
            AuditAction.USER_RESTORED,
            actor_id=actor_id,
            entity_type="user",
            entity_id=user.id,
            description=f"Restored account {user.user_code}",
        )
        return await self._reload(user.id)

    async def reset_password(
        self, user_id: uuid.UUID, payload: AdminPasswordReset, *, actor_id: uuid.UUID | None = None
    ) -> User:
        """Set another user's password on their behalf."""
        user = await self.get_by_id(user_id)
        self._assert_not_archived(user)

        await self.set_password(user, payload.new_password, actor_id=actor_id)
        user.force_password_change = payload.force_password_change

        revoked = 0
        if payload.revoke_sessions and self._tokens is not None:
            revoked = await self._tokens.revoke_all_for_user(user.id, reason="password_reset_by_admin")

        await self._audit.record_success(
            AuditAction.USER_PASSWORD_RESET,
            actor_id=actor_id,
            entity_type="user",
            entity_id=user.id,
            description=f"Reset the password for account {user.user_code}",
            context={
                "force_password_change": payload.force_password_change,
                "revoked_sessions": revoked,
            },
        )
        logger.info("Password reset by administrator", extra={"user_id": str(user.id)})
        return await self._reload(user.id)

    # ------------------------------------------------------------------
    # Self service
    # ------------------------------------------------------------------
    async def update_profile(
        self, user: User, payload: ProfileUpdate, *, actor_id: uuid.UUID | None = None
    ) -> User:
        """Apply a user's change to their own profile.

        The payload cannot carry an administrative field, so there is nothing to
        filter here -- see :class:`app.schemas.user.ProfileUpdate`.
        """
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return user

        await self._users.update(user, changes, actor_id=actor_id)
        await self._audit.record_success(
            AuditAction.USER_PROFILE_UPDATED,
            actor_id=actor_id,
            entity_type="user",
            entity_id=user.id,
            description="Updated own profile",
            context={"fields": sorted(changes)},
        )
        return await self._reload(user.id)

    async def set_password(self, user: User, new_password: str, *, actor_id: uuid.UUID | None = None) -> User:
        """Replace the stored credential and clear anything that outlived it."""
        user.hashed_password = hash_password(new_password)
        user.password_changed_at = utc_now()
        user.failed_login_attempts = 0
        user.locked_until = None
        # Whoever set this password satisfied the requirement to change it.
        user.force_password_change = False
        user.clear_password_reset()
        await self._users.update(user, {}, actor_id=actor_id)
        return user

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------
    async def _assert_identifiers_available(
        self, email: str, username: str, *, exclude_id: uuid.UUID | None
    ) -> None:
        """Reject a duplicate email or username before the database has to.

        The database enforces both as well. Checking here first is what turns an
        opaque integrity error into a message naming the field and, when it
        matters, saying that the conflicting account is archived rather than
        missing.
        """
        clash = await self._users.find_email_owner(email, exclude_id=exclude_id)
        if clash is not None:
            raise ConflictError(
                self._duplicate_message("email address", email, clash),
                error_code="duplicate_email",
            )

        clash = await self._users.find_username_owner(username, exclude_id=exclude_id)
        if clash is not None:
            raise ConflictError(
                self._duplicate_message("username", username, clash),
                error_code="duplicate_username",
            )

    @staticmethod
    def _duplicate_message(field: str, value: str, clash: User) -> str:
        subject = f'The {field} "{value}" is already in use'
        if clash.deleted_at is not None:
            return (
                f"{subject} by an archived account ({clash.user_code}). Restore that "
                "account instead of creating a duplicate, or choose a different value."
            )
        return f"{subject} by {clash.user_code}."

    async def _assert_org_references_usable(self, data: dict[str, Any]) -> None:
        invalid = await self._users.find_unusable_org_references(data)
        if invalid:
            names = ", ".join(invalid)
            raise ConflictError(
                (
                    f"The selected {names} does not exist, is archived, or is inactive."
                    if len(invalid) == 1
                    else f"These selections do not exist, are archived, or are inactive: {names}."
                ),
                error_code="invalid_organization_reference",
            )

    @staticmethod
    def _assert_not_archived(user: User) -> None:
        if user.deleted_at is not None:
            raise ConflictError(
                "This account is archived. Restore it before making changes.",
                error_code="record_archived",
            )

    async def _assert_may_disable(self, user: User, actor_id: uuid.UUID | None, *, verb: str) -> None:
        """Stop an administrator locking themselves, or everyone, out.

        Both cases end with nobody able to sign in and no way to fix it through
        the product, which is a support incident rather than an error message.
        """
        if actor_id is not None and user.id == actor_id:
            raise ConflictError(
                f"You cannot {verb} your own account. Ask another administrator to do it.",
                error_code="cannot_modify_self",
            )

        if user.is_active and await self._users.count_active() <= 1:
            raise ConflictError(
                f"This is the only active account, so it cannot be {verb}d. "
                "Create or activate another account first.",
                error_code="last_active_user",
            )

    async def _assert_no_linked_records(self, user: User) -> None:
        """Refuse the archive while other records still point at this user.

        Today the only such link is team management. Later modules -- employee
        records, requisitions, approvals -- add their checks here, which is why
        the message names the blocking relationship rather than being generic.
        """
        if self._teams is None:
            return

        managed = await self._teams.count_managed_by(user.id)
        if managed:
            noun = "team" if managed == 1 else "teams"
            raise ConflictError(
                f"This user manages {managed} active {noun}. Reassign "
                f"{'it' if managed == 1 else 'them'} before archiving the account.",
                error_code="has_linked_records",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _reload(self, user_id: uuid.UUID) -> User:
        """Re-read after a write so the organizational references are current."""
        refreshed = await self._users.get_with_relationships(user_id)
        if refreshed is None:  # pragma: no cover - the row was just written
            raise NotFoundError("User")
        return refreshed
