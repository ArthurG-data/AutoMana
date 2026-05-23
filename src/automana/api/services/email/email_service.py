import logging
import resend
from automana.core.config.settings import get_settings

logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    def send_reset_email(to: str, token: str) -> None:
        settings = get_settings()
        resend.api_key = settings.resend_api_key
        reset_url = f"{settings.app_base_url}/reset-password?token={token}"
        resend.Emails.send({
            "from": settings.from_email,
            "to": [to],
            "subject": "Reset your AutoMana password",
            "html": (
                f"<p>You requested a password reset for your AutoMana account.</p>"
                f'<p><a href="{reset_url}">Click here to reset your password</a></p>'
                f"<p>This link expires in 30 minutes.</p>"
                f"<p>If you didn't request this, you can safely ignore this email.</p>"
            ),
        })
        logger.info("password_reset_email_sent", extra={"to": to})
