# Fixtures deliberately use naive UTC to match User.created_at and SQLite storage.
# ruff: noqa: DTZ001

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-admin-monthly-activity")

from app.core.database import get_db
from app.core.security import create_access_token, get_current_user
from app.main import app
from app.models.user import User
from app.services.admin_statistics import get_monthly_activity_statistics


class AdminMonthlyActivityTests(unittest.TestCase):
    endpoint = "/admin/dashboard/monthly-activity"

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(self.engine.dispose)
        self.Session = sessionmaker(bind=self.engine)
        # As in the existing dashboard tests, omit unrelated PostgreSQL ARRAY
        # columns from the SQLite fixture, retaining the real queried fields.
        self.scholarships = Table(
            "scholarships", MetaData(),
            Column("id", Integer, primary_key=True),
            Column("status", String(20)),
            Column("reviewed_at", DateTime(timezone=True)),
            Column("scraped_at", DateTime(timezone=True)),
        )
        self.scholarships.create(self.engine)
        User.__table__.create(self.engine)

        def override_get_db():
            with self.Session() as db:
                yield db

        original_overrides = app.dependency_overrides.copy()
        self.addCleanup(self._restore_overrides, original_overrides)
        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        clock_patch = patch("app.services.admin_statistics.datetime", wraps=datetime)
        self.clock = clock_patch.start()
        self.addCleanup(clock_patch.stop)
        self.clock.now.return_value = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
        # Authentication fixtures predate the chart so they do not affect counts.
        self.admin_token = self._add_user(datetime(2024, 1, 1), role="admin")
        self.student_token = self._add_user(datetime(2024, 1, 1))

    def _restore_overrides(self, overrides):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)

    def _add_user(self, created_at, *, role="student", **attributes):
        with self.Session() as db:
            user = User(
                full_name="Monthly activity test user",
                email=f"user-{db.query(User).count()}@example.com",
                hashed_password="not-used",
                role=role,
                created_at=created_at,
                **attributes,
            )
            db.add(user)
            db.commit()
            return create_access_token({"sub": str(user.id), "role": role})

    def _add_scholarship(self, status="approved", *, reviewed_at=None, scraped_at=None):
        with self.engine.begin() as connection:
            connection.execute(self.scholarships.insert().values(
                status=status, reviewed_at=reviewed_at, scraped_at=scraped_at,
            ))

    def _get(self, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(self.endpoint, headers=headers)

    def _items(self):
        response = self._get(self.admin_token)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(set(response.json()), {"items"})
        return response.json()["items"]

    def test_admin_receives_exactly_12_chronological_months_including_current(self):
        items = self._items()
        self.assertEqual(len(items), 12)
        self.assertEqual(
            [(item["year"], item["month"]) for item in items],
            [(2025, month) for month in range(10, 13)]
            + [(2026, month) for month in range(1, 10)],
        )
        self.assertEqual(items[0], {
            "year": 2025, "month": 10, "month_name": "October",
            "approved_scholarships": 0, "users": 0,
        })
        self.assertEqual(items[-1]["month_name"], "September")

    def test_approval_uses_review_month_instead_of_scrape_month(self):
        self._add_scholarship(
            reviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            scraped_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
        )
        self._add_scholarship(reviewed_at=datetime(2026, 1, 31, 23, 59, 59))
        items = self._items()
        self.assertEqual(items[2]["approved_scholarships"], 0)
        self.assertEqual(items[3]["approved_scholarships"], 2)
        self.assertEqual(sum(item["approved_scholarships"] for item in items), 2)

    def test_other_statuses_are_excluded_even_with_review_dates(self):
        for status in ["pending", "rejected", "archived", "published", "APPROVED", None]:
            self._add_scholarship(status, reviewed_at=datetime(2026, 9, 1))
        self._add_scholarship(reviewed_at=datetime(2026, 9, 1))
        self.assertEqual(sum(item["approved_scholarships"] for item in self._items()), 1)

    def test_missing_review_date_falls_back_to_scraped_date(self):
        self._add_scholarship(scraped_at=datetime(2025, 11, 30))
        self._add_scholarship()  # Both timestamps missing: cannot assign a month.
        self._add_scholarship("pending", scraped_at=datetime(2025, 11, 30))
        items = self._items()
        self.assertEqual(items[1]["approved_scholarships"], 1)
        self.assertEqual(sum(item["approved_scholarships"] for item in items), 1)

    def test_review_outside_period_does_not_fall_back_to_scrape_inside_period(self):
        self._add_scholarship(
            reviewed_at=datetime(2026, 10, 1), scraped_at=datetime(2026, 9, 1),
        )
        self.assertTrue(all(item["approved_scholarships"] == 0 for item in self._items()))

    def test_users_counted_by_registration_including_all_account_types(self):
        self._add_user(datetime(2025, 12, 31, 23, 59, 59))
        self._add_user(datetime(2026, 1, 1), role="admin")
        self._add_user(datetime(2026, 1, 1), is_active=False)
        self._add_user(datetime(2026, 1, 1), is_email_verified=False)
        items = self._items()
        self.assertEqual(items[2]["users"], 1)
        self.assertEqual(items[3]["users"], 3)
        self.assertEqual(sum(item["users"] for item in items), 4)

    def test_window_edges_and_current_month(self):
        for timestamp in [
            datetime(2025, 9, 30, 23, 59, 59, 999999),
            datetime(2025, 10, 1),
            datetime(2026, 9, 1),
            datetime(2026, 9, 30, 23, 59, 59, 999999),
            datetime(2026, 10, 1),
        ]:
            self._add_user(timestamp)
            self._add_scholarship(reviewed_at=timestamp)
        items = self._items()
        for metric in ["users", "approved_scholarships"]:
            self.assertEqual(items[0][metric], 1)
            self.assertEqual(items[-1][metric], 2)
            self.assertEqual(sum(item[metric] for item in items), 3)

    def test_empty_database_and_undated_users_return_zero_months(self):
        with self.Session() as db:
            db.query(User).delete()
            db.commit()
        app.dependency_overrides[get_current_user] = lambda: User(id=1, role="admin")
        self.assertTrue(all(
            item["users"] == item["approved_scholarships"] == 0
            for item in self._items()
        ))
        self._add_user(datetime(2026, 1, 1))
        with self.Session() as db:
            db.query(User).update({User.created_at: None})
            db.commit()
        self.assertTrue(all(item["users"] == 0 for item in self._items()))

    def test_january_rollover_and_leap_year(self):
        self.clock.now.return_value = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self._add_user(datetime(2024, 2, 29, 23, 59, 59))
        self._add_scholarship(reviewed_at=datetime(2024, 2, 29, 23, 59, 59))
        items = self._items()
        self.assertEqual(len(items), 12)
        self.assertEqual((items[0]["year"], items[0]["month"]), (2024, 2))
        self.assertEqual((items[-1]["year"], items[-1]["month"]), (2025, 1))
        self.assertEqual(items[0]["users"], 1)
        self.assertEqual(items[0]["approved_scholarships"], 1)

    def test_unauthenticated_and_invalid_tokens_rejected(self):
        for token in [None, "invalid-token", create_access_token({"sub": "99999"})]:
            with self.subTest(token=token):
                self.assertEqual(self._get(token).status_code, 401)

    def test_non_admin_rejected_even_with_admin_role_in_token(self):
        with self.Session() as db:
            student = db.query(User).filter(User.role == "student").one()
            misleading_token = create_access_token({"sub": str(student.id), "role": "admin"})
        for token in [self.student_token, misleading_token]:
            response = self._get(token)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json(), {
                "detail": "This operation is restricted to administrators.",
            })

    def test_two_aggregate_queries_with_no_per_month_queries(self):
        statements = []

        def record_query(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", record_query)
        self.addCleanup(event.remove, self.engine, "before_cursor_execute", record_query)
        self._items()
        self.assertEqual(len(statements), 3)  # Auth lookup + two aggregate queries.
        self.assertEqual(sum("count(CASE" in statement for statement in statements), 2)

    @unittest.skipUnless(
        os.getenv("MONTHLY_ACTIVITY_TEST_DATABASE_URL"),
        "Requires a disposable local PostgreSQL database.",
    )
    def test_postgres_utc_month_boundaries_ignore_session_timezone(self):
        engine = create_engine(os.environ["MONTHLY_ACTIVITY_TEST_DATABASE_URL"])
        self.addCleanup(engine.dispose)
        self.assertIn(engine.url.host, {"localhost", "127.0.0.1"})
        self.assertTrue(engine.url.database.startswith("scholarai_monthly_test"))
        with engine.connect() as connection, connection.begin(), Session(bind=connection) as db:
            # Connection-local temporary tables need no migrations or durable data.
            connection.execute(text(
                "CREATE TEMP TABLE scholarships (id INTEGER PRIMARY KEY, status TEXT, "
                "reviewed_at TIMESTAMPTZ, scraped_at TIMESTAMPTZ) ON COMMIT DROP"
            ))
            connection.execute(text(
                "CREATE TEMP TABLE users (id INTEGER PRIMARY KEY, "
                "created_at TIMESTAMP) ON COMMIT DROP"
            ))
            connection.execute(text("""
                INSERT INTO scholarships VALUES
                    (1, 'approved', '2026-01-01 01:00:00+03', NULL),
                    (2, 'approved', '2025-12-31 23:00:00-02', NULL),
                    (3, 'approved', NULL, '2026-01-01 01:00:00+03'),
                    (4, 'pending', '2026-01-01 00:00:00+00', NULL),
                    (5, 'approved', '2025-10-01 01:00:00+03', NULL),
                    (6, 'approved', '2026-10-01 01:00:00+03', NULL)
            """))
            connection.execute(text("""
                INSERT INTO users VALUES
                    (1, '2025-12-31 23:59:59.999999'),
                    (2, '2026-01-01 00:00:00'),
                    (3, '2025-09-30 23:59:59.999999'),
                    (4, '2026-09-30 23:59:59.999999'),
                    (5, '2026-10-01 00:00:00')
            """))
            for zone in ["UTC", "Asia/Hebron", "America/Los_Angeles"]:
                with self.subTest(timezone=zone):
                    connection.execute(text("SELECT set_config('TimeZone', :zone, true)"), {"zone": zone})
                    items = get_monthly_activity_statistics(db).items
                    self.assertEqual(len(items), 12)
                    self.assertEqual(items[2].approved_scholarships, 2)
                    self.assertEqual(items[3].approved_scholarships, 1)
                    self.assertEqual(items[-1].approved_scholarships, 1)
                    self.assertEqual(sum(item.approved_scholarships for item in items), 4)
                    self.assertEqual(items[2].users, 1)
                    self.assertEqual(items[3].users, 1)
                    self.assertEqual(items[-1].users, 1)
                    self.assertEqual(sum(item.users for item in items), 3)


if __name__ == "__main__":
    unittest.main()
