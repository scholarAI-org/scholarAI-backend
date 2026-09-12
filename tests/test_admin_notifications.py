import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "notification-tests-secret-at-least-32-bytes")

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models import Scholarship, User
from app.models.admin_notification import (
    AdminNotification,
    AdminNotificationRead,
    NotificationActionType,
    NotificationType,
)
from app.services.admin_notifications import (
    create_admin_notification,
)


@pytest.fixture(params=["sqlite", "postgres"])
def notification_api(request):
    if request.param == "postgres":
        url = os.getenv("NOTIFICATIONS_TEST_DATABASE_URL")
        if not url:
            pytest.skip("Requires a disposable local PostgreSQL notification database")
        engine = create_engine(url)
        assert engine.url.host in {"localhost", "127.0.0.1"}
        assert engine.url.database.startswith("scholarai_notifications_test")
        # Exercise migrated PostgreSQL tables, not create_all.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE admin_notification_reads, admin_notifications, scholarships, users RESTART IDENTITY CASCADE"
                )
            )
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        for model in (User, AdminNotification, AdminNotificationRead):
            model.__table__.create(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    with sessions() as db:
        for identity, role in ((1, "admin"), (2, "admin"), (3, "student")):
            db.add(
                User(
                    id=identity,
                    full_name=role,
                    email=f"{identity}@example.com",
                    hashed_password="unused",
                    role=role,
                )
            )
        db.commit()
    tokens = {
        i: {"Authorization": f"Bearer {create_access_token({'sub': str(i)})}"}
        for i in (1, 2, 3)
    }
    previous = app.dependency_overrides.copy()

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client, sessions, tokens, engine
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)
    engine.dispose()


def create(sessions, **overrides):
    values = {
        "notification_type": NotificationType.GENERAL,
        "title": "Notice",
        "message": "Message",
    }
    values.update(overrides)
    with sessions() as db:
        item = create_admin_notification(db, **values)
        identity = item.id
        db.commit()
        return identity


def test_creation_validation_optional_fields_and_rollback(notification_api):
    client, sessions, tokens, _ = notification_api
    identity = create(sessions)
    item = client.get("/admin/notifications", headers=tokens[1]).json()["items"][0]
    assert item == {
        "id": identity,
        "type": "general",
        "title": "Notice",
        "message": "Message",
        "created_at": item["created_at"],
        "is_read": False,
        "related_entity_id": None,
        "action_type": None,
    }
    with sessions() as db:
        for values in (
            {"notification_type": "invalid"},
            {"action_type": "invalid"},
            {"recipient_id": 3},
            {"recipient_id": 999},
            {"title": " "},
            {"event_key": ""},
        ):
            args = {
                "notification_type": NotificationType.GENERAL,
                "title": "Title",
                "message": "Body",
            }
            args.update(values)
            with pytest.raises(ValueError):
                create_admin_notification(db, **args)
        create_admin_notification(
            db,
            notification_type=NotificationType.SCHOLARSHIP_REVIEW,
            title="Rolled back",
            message="Body",
            related_entity_id=123,
            action_type=NotificationActionType.OPEN_SCHOLARSHIP_REVIEW,
        )
        db.rollback()
    with sessions() as db:
        assert db.query(AdminNotification).count() == 1


def test_idempotency_is_scoped_to_event_type_and_audience(notification_api):
    _, sessions, _, _ = notification_api
    identity = create(sessions, event_key="event:42", recipient_id=1)
    assert create(sessions, event_key="event:42", recipient_id=1) == identity
    assert create(sessions, event_key="event:42", recipient_id=2) != identity
    assert create(sessions, event_key="event:42") != identity
    assert (
        create(
            sessions,
            event_key="event:42",
            recipient_id=1,
            notification_type=NotificationType.SCHOLARSHIP,
        )
        != identity
    )
    assert create(sessions) != create(sessions)
    with sessions() as db:
        assert db.query(AdminNotification).count() == 6


def test_pagination_filters_order_and_visibility(notification_api):
    client, sessions, tokens, engine = notification_api
    ids = [
        create(
            sessions,
            notification_type=NotificationType.SCHOLARSHIP
            if i % 2
            else NotificationType.GENERAL,
        )
        for i in range(5)
    ]
    private = create(sessions, recipient_id=2)
    with sessions() as db:
        db.query(AdminNotification).update(
            {"created_at": datetime(2026, 9, 12, tzinfo=timezone.utc)}
        )
        db.commit()
    assert (
        client.patch(
            f"/admin/notifications/{ids[3]}/read", headers=tokens[1]
        ).status_code
        == 200
    )
    response = client.get("/admin/notifications?page=2&page_size=2", headers=tokens[1])
    assert response.status_code == 200
    body = response.json()
    assert [i["id"] for i in body["items"]] == [ids[2], ids[1]]
    assert {k: body[k] for k in ("total", "page", "page_size", "total_pages")} == {
        "total": 5,
        "page": 2,
        "page_size": 2,
        "total_pages": 3,
    }
    cases = [
        ({}, list(reversed(ids))),
        ({"is_read": "true"}, [ids[3]]),
        ({"is_read": "false"}, [ids[4], ids[2], ids[1], ids[0]]),
        ({"type": "scholarship"}, [ids[3], ids[1]]),
        ({"type": "scholarship", "is_read": "false"}, [ids[1]]),
        ({"type": "general", "is_read": "true"}, []),
    ]
    for params, expected in cases:
        result = client.get(
            "/admin/notifications", headers=tokens[1], params=params
        ).json()
        assert [i["id"] for i in result["items"]] == expected
        assert result["total"] == len(expected)
        assert result["total_pages"] == (1 if expected else 0)
    assert private in [
        i["id"]
        for i in client.get("/admin/notifications", headers=tokens[2]).json()["items"]
    ]
    # Date takes precedence over ID, and reading does not affect order.
    with sessions() as db:
        db.query(AdminNotification).filter_by(id=ids[0]).update(
            {"created_at": datetime(2026, 9, 13, tzinfo=timezone.utc)}
        )
        db.commit()
    statements = []

    def capture(_, __, statement, *args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        body = client.get("/admin/notifications", headers=tokens[1]).json()
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert body["items"][0]["id"] == ids[0]
    assert (
        len([s for s in statements if s.lstrip().upper().startswith("SELECT")]) == 3
    )  # Auth, count, page
    assert (
        client.get("/admin/notifications?page=100", headers=tokens[1]).json()["items"]
        == []
    )


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page=-1",
        "page=x",
        "page_size=0",
        "page_size=101",
        "page_size=-2",
        "type=invalid",
        "is_read=invalid",
    ],
)
def test_invalid_queries(notification_api, query):
    client, _, tokens, _ = notification_api
    assert (
        client.get(f"/admin/notifications?{query}", headers=tokens[1]).status_code
        == 422
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/admin/notifications"),
        ("patch", "/admin/notifications/1/read"),
        ("get", "/admin/notifications/unread-count"),
    ],
)
def test_authentication_and_authorization(notification_api, method, path):
    client, _, tokens, _ = notification_api
    request = getattr(client, method)
    assert request(path).status_code == 401
    assert request(path, headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert request(path, headers=tokens[3]).status_code == 403


def test_read_state_isolation_first_timestamp_and_counter_contract(notification_api):
    client, sessions, tokens, _ = notification_api
    shared = create(sessions)
    private = create(sessions, recipient_id=2)
    counter = "/admin/notifications/unread-count"
    assert client.get(counter, headers=tokens[1]).json() == {"unread_count": 1}
    assert client.get(counter, headers=tokens[2]).json() == {"unread_count": 2}
    first = client.patch(f"/admin/notifications/{shared}/read", headers=tokens[1])
    assert first.status_code == 200
    assert first.json()["is_read"] is True
    assert first.json()["read_at"]
    assert (
        client.patch(f"/admin/notifications/{shared}/read", headers=tokens[1]).json()
        == first.json()
    )
    assert client.get(counter, headers=tokens[1]).json() == {"unread_count": 0}
    assert client.get(counter, headers=tokens[2]).json() == {"unread_count": 2}
    for identity in (private, 999999):
        response = client.patch(
            f"/admin/notifications/{identity}/read", headers=tokens[1]
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "Notification not found"}
    # A forged admin_id cannot select another admin's state.
    assert (
        client.get("/admin/notifications?admin_id=2", headers=tokens[1]).json()["total"]
        == 1
    )
    with sessions() as db:
        assert db.query(AdminNotificationRead).count() == 1
        assert db.get(AdminNotification, shared).is_read is False
        assert db.get(AdminNotification, shared).read_at is None


def test_legacy_read_baseline_and_future_admin(notification_api):
    client, sessions, tokens, _ = notification_api
    with sessions() as db:
        db.add(
            AdminNotification(
                title="Legacy",
                message="Legacy",
                notification_type="old_custom_type",
                is_read=True,
                read_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        )
        db.commit()
    identity = create(sessions)
    with sessions() as db:
        db.add(
            User(
                id=4,
                full_name="Future",
                email="future@example.com",
                hashed_password="unused",
                role="admin",
            )
        )
        db.commit()
    client.patch(f"/admin/notifications/{identity}/read", headers=tokens[1])
    headers = {"Authorization": f"Bearer {create_access_token({'sub': '4'})}"}
    assert client.get("/admin/notifications/unread-count", headers=headers).json() == {
        "unread_count": 1
    }
    read = client.get("/admin/notifications?is_read=true", headers=headers).json()[
        "items"
    ]
    assert len(read) == 1 and read[0]["type"] == "old_custom_type"
    response = client.patch(
        f"/admin/notifications/{read[0]['id']}/read", headers=headers
    )
    assert response.json()["read_at"].startswith("2026-01-01")


def test_openapi(notification_api):
    schema = app.openapi()
    params = {
        p["name"]: p["schema"]
        for p in schema["paths"]["/admin/notifications"]["get"]["parameters"]
    }
    assert params["page"]["default"] == 1
    assert params["page_size"]["default"] == 20
    assert params["page_size"]["maximum"] == 100
    assert "type" in params and "is_read" in params and "admin_id" not in params
    assert schema["paths"]["/admin/notifications/{notification_id}/read"]["patch"][
        "security"
    ]


def test_real_ingestion_and_atomic_failure(notification_api):
    client, sessions, tokens, engine = notification_api
    if engine.dialect.name != "postgresql":
        pytest.skip("Scholarship ingestion uses native PostgreSQL ARRAY columns")
    for source in ("for9a", "ministry"):
        payload = {
            "source": source,
            "source_id": "source-42",
            "title": f"{source} scholarship",
        }
        response = client.post("/api/scholarships/", headers=tokens[1], json=payload)
        assert response.status_code == 201, response.text
        scholarship_id = response.json()["id"]
        with sessions() as db:
            notice = (
                db.query(AdminNotification)
                .filter_by(related_entity_id=scholarship_id)
                .one()
            )
            assert notice.notification_type == "scholarship_review"
            assert notice.title == "New scholarship pending review"
            assert payload["title"] in notice.message
            assert notice.action_type == "open_scholarship_review"
            assert notice.is_read is False
        assert (
            client.post(
                "/api/scholarships/", headers=tokens[1], json=payload
            ).status_code
            == 409
        )
    for source, status in (
        ("manual", "pending"),
        ("for9a", "approved"),
        ("ministry", "rejected"),
    ):
        response = client.post(
            "/api/scholarships/",
            headers=tokens[1],
            json={"source": source, "title": "No review", "status": status},
        )
        assert response.status_code == 201
    with sessions() as db:
        assert db.query(AdminNotification).count() == 2
        before = db.query(Scholarship).count()
    original = create_admin_notification

    def fail_after_insert(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Notification failed after insert")

    with (
        patch(
            "app.api.scholarships.create_admin_notification",
            side_effect=fail_after_insert,
        ),
        pytest.raises(RuntimeError, match="Notification failed"),
    ):
        client.post(
            "/api/scholarships/",
            headers=tokens[1],
            json={"source": "for9a", "source_id": "failed", "title": "Rollback"},
        )
    with sessions() as db:
        assert db.query(Scholarship).count() == before
        assert db.query(AdminNotification).count() == 2


def test_concurrent_event_and_read_requests(notification_api):
    client, sessions, tokens, engine = notification_api
    if engine.dialect.name != "postgresql":
        pytest.skip("Concurrency uses independent PostgreSQL connections")
    barrier = Barrier(4)

    def write_event(_):
        barrier.wait(timeout=10)
        return create(sessions, event_key="concurrent-event")

    with ThreadPoolExecutor(max_workers=4) as pool:
        identities = list(pool.map(write_event, range(4)))
    assert len(set(identities)) == 1
    barrier = Barrier(4)

    def read_event(_):
        barrier.wait(timeout=10)
        response = client.patch(
            f"/admin/notifications/{identities[0]}/read", headers=tokens[1]
        )
        assert response.status_code == 200
        return response.json()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(read_event, range(4)))
    assert all(result == results[0] for result in results)
    with sessions() as db:
        assert db.query(AdminNotification).count() == 1
        assert db.query(AdminNotificationRead).count() == 1
