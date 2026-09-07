import json
import os
import unittest
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

POSTGRES_TEST_DATABASE_URL = os.getenv("PROFILE_CONSTRAINT_TEST_DATABASE_URL")


@unittest.skipUnless(
    POSTGRES_TEST_DATABASE_URL,
    "Set PROFILE_CONSTRAINT_TEST_DATABASE_URL to a migrated disposable PostgreSQL database.",
)
class ProfileListConstraintTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(POSTGRES_TEST_DATABASE_URL)
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.user_id = self.connection.execute(
            text(
                """
                INSERT INTO users (full_name, email, hashed_password)
                VALUES ('Constraint Test', :email, 'x')
                RETURNING id
                """
            ),
            {"email": f"constraint-{uuid.uuid4()}@example.com"},
        ).scalar_one()

    def tearDown(self):
        self.connection.rollback()
        self.connection.close()
        self.engine.dispose()

    def _insert_profile(self, languages, skills):
        self.connection.execute(
            text(
                """
                INSERT INTO profiles (user_id, languages_data, skills_data)
                VALUES (:user_id, CAST(:languages AS json), CAST(:skills AS json))
                """
            ),
            {
                "user_id": self.user_id,
                "languages": json.dumps(languages),
                "skills": json.dumps(skills),
            },
        )

    def test_database_accepts_unique_valid_values(self):
        self._insert_profile(
            [
                {"name": "English", "proficiency": "ADVANCED"},
                {"name": "French", "proficiency": "BEGINNER"},
            ],
            ["Python", "SQL"],
        )

    def test_database_rejects_normalized_duplicates(self):
        invalid_values = [
            (
                [
                    {"name": "English", "proficiency": "ADVANCED"},
                    {"name": " english ", "proficiency": "NATIVE"},
                ],
                [],
                "ck_profiles_languages_valid_unique_normalized",
            ),
            ([], ["Python", " python "], "ck_profiles_skills_valid_unique_normalized"),
        ]

        for languages, skills, constraint in invalid_values:
            with (
                self.subTest(constraint=constraint),
                self.assertRaises(IntegrityError) as raised,
                self.connection.begin_nested(),
            ):
                self._insert_profile(languages, skills)
            self.assertIn(constraint, str(raised.exception.orig))

    def test_database_rejects_malformed_values(self):
        with self.assertRaises(IntegrityError):
            self._insert_profile(
                [{"name": "  ", "proficiency": "UNKNOWN"}],
                [""],
            )


if __name__ == "__main__":
    unittest.main()
