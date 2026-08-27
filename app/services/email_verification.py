import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.models.user import User


def generate_otp() -> str:
    """Return a cryptographically secure six-digit OTP."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        otp.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def otp_matches(otp: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(otp), expected_hash)


def utc_now_naive() -> datetime:
    """Return naive UTC to match the project's existing DateTime columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def issue_verification_otp(
    user: User,
    *,
    now: datetime | None = None,
) -> str:
    issued_at = now or utc_now_naive()
    otp = generate_otp()
    while (
        user.email_verification_otp_hash
        and otp_matches(otp, user.email_verification_otp_hash)
    ):
        otp = generate_otp()
    user.email_verification_otp_hash = hash_otp(otp)
    user.email_verification_otp_expires_at = issued_at + timedelta(
        minutes=settings.EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES
    )
    user.email_verification_otp_sent_at = issued_at
    return otp


def clear_verification_otp(user: User) -> None:
    user.email_verification_otp_hash = None
    user.email_verification_otp_expires_at = None
    user.email_verification_otp_sent_at = None
