import os
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-review-details-only")

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.user import User


class ScholarshipReviewDetailsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        self.addCleanup(self.engine.dispose)
        factory = sessionmaker(bind=self.engine)
        User.__table__.create(self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE scholarships (id INTEGER PRIMARY KEY, title TEXT, "
                    "organization_name TEXT, country TEXT, description_html TEXT)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO scholarships VALUES "
                    "(1, 'First scholarship', 'First organization', 'Palestine', '<p>First</p>'), "
                    "(2, 'Second scholarship', 'Second organization', 'Turkey', '<p>Second</p>'), "
                    "(3, 'Missing details', NULL, NULL, NULL)"
                )
            )
        with factory() as db:
            db.add_all(
                [
                    User(
                        id=1,
                        full_name="Admin",
                        email="admin@example.com",
                        hashed_password="unused",
                        role="admin",
                    ),
                    User(
                        id=2,
                        full_name="Student",
                        email="student@example.com",
                        hashed_password="unused",
                        role="student",
                    ),
                ]
            )
            db.commit()

        def override_db():
            with factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        self.addCleanup(app.dependency_overrides.pop, get_db)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.queries = []
        event.listen(self.engine, "before_cursor_execute", self.record_query)

    def record_query(self, conn, cursor, statement, parameters, context, executemany):
        self.queries.append(statement)

    def get_details(self, scholarship_id=1, user_id=1):
        # A claimed admin role must never override the actual user's stored role.
        token = create_access_token({"sub": str(user_id), "role": "admin"})
        return self.client.get(
            f"/admin/scholarships/{scholarship_id}/review-details",
            headers={"Authorization": f"Bearer {token}"},
        )

    def test_admin_gets_exact_fields_for_requested_id(self):
        for scholarship_id, name, country in [
            (1, "First", "Palestine"),
            (2, "Second", "Turkey"),
        ]:
            with self.subTest(scholarship_id=scholarship_id):
                response = self.get_details(scholarship_id)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.json(),
                    {
                        "title": f"{name} scholarship",
                        "organization_name": f"{name} organization",
                        "country": country,
                        "description": f"<p>{name}</p>",
                        "additional_details": None,
                    },
                )

    def test_null_values(self):
        response = self.get_details(3)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "title": "Missing details",
                "organization_name": None,
                "country": None,
                "description": None,
                "additional_details": None,
            },
        )

    def test_missing_scholarship(self):
        response = self.get_details(999)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Scholarship not found"})

    def test_unauthenticated(self):
        response = self.client.get("/admin/scholarships/1/review-details")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.queries, [])

    def test_invalid_token(self):
        response = self.client.get(
            "/admin/scholarships/1/review-details",
            headers={"Authorization": "Bearer invalid"},
        )
        self.assertEqual(response.status_code, 401)

    def test_student_rejected_even_with_admin_claim(self):
        for scholarship_id in (1, 999):
            self.assertEqual(
                self.get_details(scholarship_id, user_id=2).status_code, 403
            )
        self.assertFalse(any("scholarships" in query for query in self.queries))

    def test_single_scholarship_query(self):
        self.assertEqual(self.get_details().status_code, 200)
        self.assertEqual(sum("FROM scholarships" in query for query in self.queries), 1)

    def test_invalid_id(self):
        self.assertEqual(self.get_details("invalid").status_code, 422)

    def test_openapi_contract(self):
        from fastapi.openapi.models import OpenAPI

        schema = self.client.get("/openapi.json").json()
        OpenAPI.model_validate(schema)
        operation = schema["paths"][
            "/admin/scholarships/{scholarship_id}/review-details"
        ]["get"]
        self.assertEqual(operation["security"], [{"HTTPBearer": []}])
        self.assertEqual(
            [(p["name"], p["in"]) for p in operation["parameters"]],
            [("scholarship_id", "path")],
        )
        properties = schema["components"]["schemas"][
            "ScholarshipReviewDetailsResponse"
        ]["properties"]
        self.assertEqual(
            set(properties),
            {
                "title",
                "organization_name",
                "country",
                "description",
                "additional_details",
            },
        )
        for field in properties.values():
            self.assertIn({"type": "null"}, field["anyOf"])
        self.assertTrue(
            {"200", "401", "403", "404", "422"} <= set(operation["responses"])
        )
