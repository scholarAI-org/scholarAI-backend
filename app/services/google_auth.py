from dataclasses import dataclass
from typing import Any

try:
    from google.auth.transport import requests
    from google.oauth2 import id_token
except ImportError:  # pragma: no cover
    requests = None
    id_token = None

from app.core.config import settings


class GoogleCredentialError(ValueError):
    pass


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    full_name: str
    picture: str | None = None


def verify_google_id_token(credential: str) -> GoogleIdentity:
    """Verify a Google ID token and return only trusted identity claims."""
    if not settings.GOOGLE_CLIENT_ID:
        raise RuntimeError("Google authentication is not configured")

    try:
        claims: dict[str, Any] = id_token.verify_oauth2_token(
            credential,
            requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError as exc:
        # The library validates signature, expiration, and audience.
        raise GoogleCredentialError("Invalid Google credential") from exc

    if claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise GoogleCredentialError("Invalid Google credential issuer")
    if claims.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise GoogleCredentialError("Invalid Google credential audience")
    if claims.get("email_verified") is not True:
        raise GoogleCredentialError("Google email is not verified")

    subject = claims.get("sub")
    email = claims.get("email")
    if not isinstance(subject, str) or not subject or not isinstance(email, str) or not email:
        raise GoogleCredentialError("Google credential is missing required claims")

    name = claims.get("name")
    return GoogleIdentity(
        subject=subject,
        email=email.strip().lower(),
        full_name=name.strip() if isinstance(name, str) and name.strip() else email,
        picture=claims.get("picture") if isinstance(claims.get("picture"), str) else None,
    )
