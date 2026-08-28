"""Outbound email.

A minimal SMTP sender with a console fallback, so every mail flow is fully
exercisable locally without a mail server. Deliberately small: the platform
speaks through the in-app notification inbox, and email is reserved for the
messages that cannot land there -- password flows (the user may be locked out)
and the preboarding invitation (the recipient has no account yet). Swapping in
a transactional provider later means replacing :meth:`MailService._deliver`
only.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from urllib.parse import quote

import anyio

from app.core.config import settings
from app.core.logging import get_logger
from app.utils.strings import mask_email

logger = get_logger("services.mail")


class MailService:
    """Sends the small set of transactional emails the platform needs."""

    async def send_password_reset(self, *, to_email: str, full_name: str, reset_token: str) -> None:
        reset_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={quote(reset_token)}"
        expiry_minutes = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES

        subject = f"Reset your {settings.APP_NAME} password"
        body = (
            f"Hello {full_name},\n\n"
            f"We received a request to reset your {settings.APP_NAME} password.\n"
            f"Use the link below within {expiry_minutes} minutes to choose a new one:\n\n"
            f"{reset_url}\n\n"
            "If you did not request this, you can safely ignore this email — "
            "your password will remain unchanged.\n\n"
            f"— The {settings.APP_NAME} team\n"
        )
        await self._deliver(to_email=to_email, subject=subject, body=body)

    async def send_password_changed_notice(self, *, to_email: str, full_name: str) -> None:
        subject = f"Your {settings.APP_NAME} password was changed"
        body = (
            f"Hello {full_name},\n\n"
            "Your password was changed and all other active sessions were signed out.\n"
            "If this wasn't you, contact your administrator immediately.\n\n"
            f"— The {settings.APP_NAME} team\n"
        )
        await self._deliver(to_email=to_email, subject=subject, body=body)

    async def send_preboarding_invitation(
        self, *, to_email: str, full_name: str, portal_url: str, joining_date: str | None
    ) -> None:
        """The one message that cannot be delivered in-app: the recipient has
        no account yet. Everything else the platform says lands in the
        notification inbox; a new joiner's invitation has to travel outside.
        """
        subject = f"Welcome to {settings.APP_NAME} — your preboarding portal"
        joining_line = f"Your joining date is {joining_date}.\n\n" if joining_date else ""
        body = (
            f"Hello {full_name},\n\n"
            "Congratulations on your offer! Your preboarding portal is ready:\n\n"
            f"{portal_url}\n\n"
            f"{joining_line}"
            "You can review your details and see what to bring on your first day.\n\n"
            f"— The {settings.APP_NAME} team\n"
        )
        await self._deliver(to_email=to_email, subject=subject, body=body)

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------
    async def _deliver(self, *, to_email: str, subject: str, body: str) -> None:
        if not settings.SMTP_HOST:
            logger.info(
                "SMTP not configured; email written to the log instead",
                extra={"recipient": mask_email(to_email), "subject": subject, "body": body},
            )
            return

        message = EmailMessage()
        message["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        try:
            # smtplib is blocking; keep the event loop free.
            await anyio.to_thread.run_sync(self._send_sync, message)
            logger.info("Email sent", extra={"recipient": mask_email(to_email), "subject": subject})
        except (smtplib.SMTPException, OSError):
            # A mail outage must not surface as a failed password reset request:
            # the caller has already persisted the token.
            logger.error(
                "Failed to send email",
                extra={"recipient": mask_email(to_email), "subject": subject},
                exc_info=True,
            )

    @staticmethod
    def _send_sync(message: EmailMessage) -> None:
        with smtplib.SMTP(settings.SMTP_HOST or "", settings.SMTP_PORT, timeout=15) as client:
            if settings.SMTP_TLS:
                client.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                client.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            client.send_message(message)
