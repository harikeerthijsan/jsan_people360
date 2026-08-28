"""Authentication endpoints.

Routes are intentionally thin: validate input (Pydantic), delegate to
``AuthService``, translate the result into the standard envelope, and manage the
refresh-token cookie. No business rules appear in this module.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import AuthSvc, AuthzSvc, CurrentUser, Origin, RefreshCookie
from app.core.config import settings
from app.core.exceptions import InvalidTokenError
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    PasswordResetIssued,
    RefreshRequest,
    ResetPasswordRequest,
)
from app.schemas.common import APIErrorResponse, APIResponse, MessageData
from app.schemas.rbac import RoleSummary, SessionRead
from app.schemas.user import UserRead
from app.services.token_service import IssuedTokens
from app.utils.datetime import seconds_until

router = APIRouter(prefix="/auth", tags=["Authentication"])

_AUTH_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": APIErrorResponse, "description": "Authentication failed."},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": APIErrorResponse, "description": "Validation failed."},
}


def _set_refresh_cookie(response: Response, tokens: IssuedTokens) -> None:
    """Store the refresh token in an HttpOnly cookie.

    Keeping it out of the response body means JavaScript -- and therefore an XSS
    payload -- cannot read it. The cookie path is scoped to the auth routes so it
    is not attached to every API call.
    """
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=tokens.refresh_token,
        max_age=seconds_until(tokens.refresh_expires_at),
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )


@router.post(
    "/login",
    response_model=APIResponse[LoginResponse],
    status_code=status.HTTP_200_OK,
    summary="Sign in",
    description=(
        "Exchanges email and password for a short-lived access token. "
        "The refresh token is returned as an HttpOnly cookie, never in the body."
    ),
    responses=_AUTH_ERROR_RESPONSES,
)
async def login(
    payload: LoginRequest,
    service: AuthSvc,
    origin: Origin,
    response: Response,
) -> APIResponse[LoginResponse]:
    session = await service.login(payload, origin)
    _set_refresh_cookie(response, session.tokens)

    return APIResponse.ok(
        LoginResponse(tokens=session.tokens.token_pair, user=UserRead.from_user(session.user)),
        message="Signed in successfully",
    )


@router.post(
    "/refresh",
    response_model=APIResponse[LoginResponse],
    summary="Rotate the session",
    description=(
        "Exchanges a valid refresh token for a new token pair. The presented token is "
        "revoked; replaying it invalidates every session for that user."
    ),
    responses=_AUTH_ERROR_RESPONSES,
)
async def refresh_session(
    service: AuthSvc,
    origin: Origin,
    response: Response,
    cookie_token: RefreshCookie,
    payload: RefreshRequest | None = None,
) -> APIResponse[LoginResponse]:
    raw_token = (payload.refresh_token if payload else None) or cookie_token
    if not raw_token:
        raise InvalidTokenError("No refresh token was supplied.")

    session = await service.refresh(raw_token, origin)
    _set_refresh_cookie(response, session.tokens)

    return APIResponse.ok(
        LoginResponse(tokens=session.tokens.token_pair, user=UserRead.from_user(session.user)),
        message="Session refreshed successfully",
    )


@router.post(
    "/logout",
    response_model=APIResponse[MessageData],
    summary="Sign out",
    description="Revokes the current refresh token, or every active session when `all_sessions` is true.",
)
async def logout(
    service: AuthSvc,
    current_user: CurrentUser,
    response: Response,
    cookie_token: RefreshCookie,
    payload: LogoutRequest | None = None,
) -> APIResponse[MessageData]:
    all_sessions = payload.all_sessions if payload else False
    await service.logout(
        raw_refresh_token=cookie_token,
        user_id=current_user.id,
        all_sessions=all_sessions,
    )
    _clear_refresh_cookie(response)

    detail = "Signed out of all sessions." if all_sessions else "Signed out successfully."
    return APIResponse.ok(MessageData(detail=detail), message=detail)


@router.get(
    "/me",
    response_model=APIResponse[SessionRead],
    summary="Current session",
    description=(
        "The authenticated caller's profile, the roles they hold and every permission "
        "those roles grant. The permissions travel with the profile rather than on a "
        "second request because the first render already needs them -- the shell decides "
        "which navigation items exist -- and fetching them separately would show a flash "
        "of menu entries the user cannot open."
    ),
    responses=_AUTH_ERROR_RESPONSES,
)
async def read_current_user(current_user: CurrentUser, authorization: AuthzSvc) -> APIResponse[SessionRead]:
    session = SessionRead(
        user=UserRead.from_user(current_user),
        roles=[RoleSummary.model_validate(role) for role in await authorization.roles_for(current_user)],
        permissions=sorted(await authorization.permissions_for(current_user)),
        is_superuser=current_user.is_superuser,
    )
    return APIResponse.ok(session, message="Profile retrieved successfully")


@router.post(
    "/forgot-password",
    response_model=APIResponse[PasswordResetIssued],
    summary="Request a password reset",
    description=(
        "Emails a single-use reset link. Always returns 200 regardless of whether the "
        "address is registered, so the endpoint cannot be used to enumerate accounts. "
        "Outside production the raw token is included in the response to make the flow "
        "testable without a mail server."
    ),
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    service: AuthSvc,
) -> APIResponse[PasswordResetIssued]:
    raw_token = await service.request_password_reset(payload.email)

    detail = "If an account exists for that address, a password reset link has been sent."
    return APIResponse.ok(
        PasswordResetIssued(
            detail=detail,
            reset_token=raw_token if (raw_token and not settings.is_production) else None,
        ),
        message=detail,
    )


@router.post(
    "/reset-password",
    response_model=APIResponse[MessageData],
    summary="Complete a password reset",
    description="Consumes a reset token, sets the new password and revokes every existing session.",
    responses=_AUTH_ERROR_RESPONSES,
)
async def reset_password(
    payload: ResetPasswordRequest,
    service: AuthSvc,
    response: Response,
) -> APIResponse[MessageData]:
    await service.reset_password(raw_token=payload.token, new_password=payload.new_password)
    _clear_refresh_cookie(response)

    detail = "Your password has been reset. Please sign in with your new password."
    return APIResponse.ok(MessageData(detail=detail), message=detail)


@router.post(
    "/change-password",
    response_model=APIResponse[MessageData],
    summary="Change your password",
    description="Changes the password of the authenticated caller and revokes every existing session.",
    responses=_AUTH_ERROR_RESPONSES,
)
async def change_password(
    payload: ChangePasswordRequest,
    service: AuthSvc,
    current_user: CurrentUser,
    response: Response,
) -> APIResponse[MessageData]:
    await service.change_password(
        current_user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    _clear_refresh_cookie(response)

    detail = "Your password has been changed. Please sign in again."
    return APIResponse.ok(MessageData(detail=detail), message=detail)
