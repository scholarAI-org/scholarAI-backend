import re

import resend
from resend.exceptions import ResendError

from app.core.config import settings


class EmailDeliveryError(RuntimeError):
    """A provider-safe mail error that never contains the API key or recipient."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | str | None = None,
        error_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type


def _safe_error_message(message: object) -> str:
    cleaned = " ".join(str(message).split())
    if settings.RESEND_API_KEY:
        cleaned = cleaned.replace(settings.RESEND_API_KEY, "[redacted-api-key]")
    cleaned = re.sub(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        "[redacted-email]",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned[:500]


def _sender() -> str:
    from_email = settings.RESEND_FROM_EMAIL or settings.MAIL_FROM
    if not from_email:
        raise EmailDeliveryError(
            "Resend sender is not configured; set RESEND_FROM_EMAIL",
            error_type="configuration_error",
        )
    from_name = settings.MAIL_FROM_NAME or "Scholar AI"
    return f"{from_name} <{from_email}>"


def _send_email(*, email_to: str, subject: str, html: str) -> None:
    if not settings.RESEND_API_KEY:
        raise EmailDeliveryError(
            "Resend API key is not configured",
            error_type="configuration_error",
        )

    resend.api_key = settings.RESEND_API_KEY
    try:
        resend.Emails.send(
            {
                "from": _sender(),
                "to": [email_to],
                "subject": subject,
                "html": html,
            }
        )
    except EmailDeliveryError:
        raise
    except ResendError as exc:
        raise EmailDeliveryError(
            _safe_error_message(getattr(exc, "message", exc)),
            status_code=getattr(exc, "code", None),
            error_type=getattr(exc, "error_type", None),
        ) from None
    except Exception as exc:
        raise EmailDeliveryError(
            _safe_error_message(exc),
            error_type=type(exc).__name__,
        ) from None


def send_verification_otp_email(email_to: str, otp: str) -> None:
    """Send an email verification code without exposing it in logs or API responses."""
    html_content = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px;">
        <h2>Verify your Scholar AI email</h2>
        <p>Your email verification code is:</p>
        <p style="font-size: 28px; font-weight: bold; letter-spacing: 6px;">{otp}</p>
        <p>This code will expire in {settings.EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES} minutes.</p>
        <p>If you did not create this account, you can ignore this email.</p>
    </div>
    """
    _send_email(
        email_to=email_to,
        subject="Verify your email - Scholar AI",
        html=html_content,
    )


def send_reset_password_email(email_to: str, token: str) -> None:
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; direction: rtl; text-align: right; padding: 20px;">
        <h2>طلب إعادة تعيين كلمة المرور - Scholar AI</h2>
        <p>مرحباً، لقد تلقينا طلباً لإعادة تعيين كلمة المرور الخاصة بحسابك.</p>
        <p>اضغط/ي على الزر أدناه لتغيير كلمة المرور (الرابط صالح لمدة 15 دقيقة فقط):</p>
        <a href="{reset_link}" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; display: inline-block; border-radius: 5px; margin: 10px 0;">تغيير كلمة المرور</a>
        <br><br>
        <p>إذا لم تطلبي ذلك، يمكنكِ إهمال هذا البريد وسيظل حسابكِ آمناً.</p>
    </div>
    """
    _send_email(
        email_to=email_to,
        subject="إعادة تعيين كلمة المرور - Scholar AI",
        html=html_content,
    )
