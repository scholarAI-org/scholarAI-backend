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
        with TestClient(app) as client:
            yield client, sessions
    finally:
        engine.dispose()


@pytest.mark.parametrize(("user_id", "role"), [(1, "student"), (2, "admin")])
def test_login_returns_role_and_token_can_fetch_exact_current_user(api, user_id, role):
    client = api[0]
    login = client.post(
        "/auth/login",
        json={"email": f"{role.upper()}@example.com", "password": "Pass123!"},
    )
    assert login.status_code == 200, login.text
    data = login.json()
    assert set(data) == {"access_token", "token_type", "role"}
    assert data["token_type"] == "bearer"
    assert data["role"] == role
    claims = jwt.decode(data["access_token"], SECRET_KEY, algorithms=[ALGORITHM])
    assert claims["sub"] == str(user_id)
    assert claims["role"] == role

    response = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": user_id,
        "email": f"{role}@example.com",
        "name": f"Ahmed {role}",
        "role": role,
    }


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
    response = client.get("/auth/me", headers=headers)
    existing = client.post("/auth/logout", headers=headers)
    assert response.status_code in {401, 403}
    assert response.status_code == existing.status_code
    assert response.json() == existing.json()


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
    assert schemas["LoginResponse"]["properties"]["role"]["enum"] == ["student", "admin"]
    assert "role" in schemas["LoginResponse"]["required"]
    assert set(schemas["CurrentUserResponse"]["properties"]) == {"id", "email", "name", "role"}
    assert schema["paths"]["/auth/me"]["get"]["security"] == [{"HTTPBearer": []}]
    assert set(schemas["GoogleAuthResponse"]["properties"]) == {"access_token", "token_type", "user"}
