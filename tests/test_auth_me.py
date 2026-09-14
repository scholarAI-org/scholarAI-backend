import os
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "auth-me-test-secret-key-at-least-32-bytes")

from app.api.auth import router
from app.core.config import settings
from app.core.database import get_db
from app.core.security import ALGORITHM, SECRET_KEY, create_access_token, hash_password
from app.models.user import User


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_ENABLED", True)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    User.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    password_hash = hash_password("Pass123!")
    with sessions() as db:
        for user_id, role in ((1, "student"), (2, "admin")):
            db.add(User(
                id=user_id,
                full_name=f"Ahmed {role}",
                email=f"{role}@example.com",
                hashed_password=password_hash,
                role=role,
                is_email_verified=True,
            ))
        db.commit()

    app = FastAPI()
    app.include_router(router)

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client, sessions
    finally:
        engine.dispose()


@pytest.mark.parametrize(("user_id", "role"), [(1, "student"), (2, "admin")])
def test_login_sets_cookie_and_returns_role(api, user_id, role):
    """
    POST /auth/login should:
      - Return only { role } in the body (no token in body).
      - Set an HttpOnly cookie named 'access_token'.
      - Allow /auth/me to be accessed using that cookie.
    """
    client = api[0]
    login = client.post(
        "/auth/login",
        json={"email": f"{role.upper()}@example.com", "password": "Pass123!"},
    )
    assert login.status_code == 200, login.text
    data = login.json()

    # Token must NOT be in the response body
    assert "access_token" not in data
    assert "token_type" not in data
    assert data["role"] == role

    # Cookie must be set on the client
    assert settings.COOKIE_NAME in client.cookies

    # /auth/me must work using the cookie (no explicit Authorization header)
    me = client.get("/auth/me")
    assert me.status_code == 200, me.text
    assert me.json() == {
        "id": user_id,
        "email": f"{role}@example.com",
        "name": f"Ahmed {role}",
        "role": role,
    }


def test_me_via_bearer_fallback(api):
    """
    /auth/me must still work when a valid Bearer token is sent directly
    (fallback for direct API / test clients).
    """
    client = api[0]
    token = create_access_token({"sub": "1", "role": "student"})
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["id"] == 1


def test_me_uses_current_database_values_and_ignores_client_selected_user(api):
    client, sessions = api
    token = create_access_token({"sub": "1", "role": "student"})
    with sessions() as db:
        user = db.get(User, 1)
        user.full_name = "Updated Name"
        user.email = "updated@example.com"
        user.role = "admin"
        db.commit()
    response = client.get(
        "/auth/me?user_id=2", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": 1, "email": "updated@example.com", "name": "Updated Name", "role": "admin"
    }


@pytest.mark.parametrize("kind", ["missing", "invalid", "expired", "unknown_user"])
def test_me_rejects_missing_or_invalid_authentication(api, kind):
    client = api[0]
    if kind == "missing":
        headers = {}
    else:
        tokens = {
            "invalid": "invalid-token",
            "expired": jwt.encode(
                {"sub": "1", "exp": datetime.now(UTC) - timedelta(minutes=1)},
                SECRET_KEY,
                algorithm=ALGORITHM,
            ),
            "unknown_user": create_access_token({"sub": "999"}),
        }
        headers = {"Authorization": f"Bearer {tokens[kind]}"}

    # Ensure no cookie is set for this sub-test
    client.cookies.clear()
    response = client.get("/auth/me", headers=headers)
    assert response.status_code in {401, 403}


def test_logout_clears_cookie(api):
    """POST /auth/logout must delete the session cookie."""
    client = api[0]
    # Login first to get a cookie
    client.post(
        "/auth/login",
        json={"email": "student@example.com", "password": "Pass123!"},
    )
    assert settings.COOKIE_NAME in client.cookies

    logout = client.post("/auth/logout")
    assert logout.status_code == 200

    # Cookie must be gone
    assert settings.COOKIE_NAME not in client.cookies or client.cookies[settings.COOKIE_NAME] == ""

    # /auth/me must now reject without Bearer
    me = client.get("/auth/me")
    assert me.status_code == 401


@pytest.mark.parametrize(
    ("email", "password"),
    [("student@example.com", "Wrong123!"), ("missing@example.com", "Pass123!")],
)
def test_login_still_rejects_invalid_credentials(api, email, password):
    response = api[0].post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401
    assert set(response.json()) == {"detail"}


def test_login_still_requires_email_verification(api):
    client, sessions = api
    with sessions() as db:
        db.get(User, 1).is_email_verified = False
        db.commit()
    response = client.post(
        "/auth/login", json={"email": "student@example.com", "password": "Pass123!"}
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Email verification required"}


def test_openapi_documents_login_role_and_me_response(api):
    schema = api[0].get("/openapi.json").json()
    schemas = schema["components"]["schemas"]

    # LoginResponse must only contain 'role' — no token fields
    login_props = set(schemas["LoginResponse"]["properties"])
    assert "role" in login_props
    assert "access_token" not in login_props
    assert "token_type" not in login_props

    assert schemas["LoginResponse"]["properties"]["role"]["enum"] == ["student", "admin"]
    assert "role" in schemas["LoginResponse"]["required"]
    assert set(schemas["CurrentUserResponse"]["properties"]) == {"id", "email", "name", "role"}

    # GoogleAuthResponse must only contain 'user' — no token fields
    google_props = set(schemas["GoogleAuthResponse"]["properties"])
    assert google_props == {"user"}
