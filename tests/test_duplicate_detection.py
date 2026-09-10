import os
import unittest
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SECRET_KEY", "test-secret-key-duplicate-detection-at-least-32-chars")

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models.Scholarship import Scholarship
from app.models.user import User
from app.services.duplicate_detection import (
    calculate_text_similarity,
    compare_scholarships,
    find_duplicate_candidates,
    normalize_arabic_letters,
    normalize_text,
    normalize_url,
    tokenize,
)


class DuplicateDetectionServiceUnitTests(unittest.TestCase):
    def test_normalize_arabic_letters(self):
        raw = "مِنْحَةُ أَبْحَاثٍ إِسْلَامِيَّةٌ"
        normalized = normalize_arabic_letters(raw)
        # Tashkeel removed, Alef normalized, Taa Marbouta normalized
        self.assertNotIn("َ", normalized)
        self.assertNotIn("ِ", normalized)
        self.assertNotIn("ْ", normalized)
        self.assertIn("منحه", normalized)
        self.assertIn("ابحاث", normalized)
        self.assertIn("اسلاميه", normalized)

    def test_normalize_text_bilingual(self):
        ar_text = "  منحة جامعة إسطنبول التقنية - 2026!  "
        norm_ar = normalize_text(ar_text)
        self.assertEqual(norm_ar, "منحه جامعه اسطنبول التقنيه 2026")

        en_text = "  Chevening SCHOLARSHIPS 2026 / UK & London!  "
        norm_en = normalize_text(en_text)
        self.assertEqual(norm_en, "chevening scholarships 2026 uk london")

    def test_tokenize_stopwords_removal(self):
        text = "منحة دراسية ممولة بالكامل في جامعة أكسفورد"
        tokens = tokenize(text, remove_stop_words=True)
        # Stop words like "منحة", "دراسية", "ممولة", "بالكامل", "في", "جامعة" filtered out
        self.assertIn("اكسفورد", tokens)
        self.assertNotIn("منحه", tokens)

    def test_calculate_text_similarity_identical_and_permutations(self):
        # Exact match
        score_exact = calculate_text_similarity("منحة الحكومة التركية", "منحة الحكومة التركية")
        self.assertEqual(score_exact, 1.0)

        # Word order variation
        score_order = calculate_text_similarity(
            "جامعة إسطنبول التقنية - منحة دراسية",
            "منحة دراسية في جامعة إسطنبول التقنية",
        )
        self.assertGreaterEqual(score_order, 0.85)

        # Minor typo / Alef variation
        score_typo = calculate_text_similarity(
            "منحة جامعة اكسفورد للماجستير",
            "منحة جامعة إكسفورد للماجستير",
        )
        self.assertGreaterEqual(score_typo, 0.95)

        # Completely different scholarships
        score_diff = calculate_text_similarity(
            "منحة دراسة الطب في ألمانيا",
            "برنامج تدريب الذكاء الاصطناعي في اليابان",
        )
        self.assertLess(score_diff, 0.35)

    def test_normalize_url(self):
        url1 = "https://WWW.Example.com/apply/?utm_source=facebook&utm_medium=ad#section"
        url2 = "http://example.com/apply"
        self.assertEqual(normalize_url(url1), "https://example.com/apply")
        self.assertEqual(normalize_url(url2), "http://example.com/apply")

    def test_compare_scholarships_signals(self):
        cand = Scholarship(
            id=1,
            title="منحة الحكومة التركية 2026",
            country="تركيا",
            organization_name="Türkiye Bursları",
            apply_link="https://tbbs.turkiyeburslari.gov.tr/",
            source="for9a",
            status="approved",
        )

        # Target 1: Identical apply link from another source
        target_same_url = {
            "title": "منحة الحكومة التركية للعام 2026",
            "country": "تركيا",
            "organization_name": "Türkiye Bursları",
            "apply_link": "https://tbbs.turkiyeburslari.gov.tr/?utm_source=ministry",
        }
        score1, reasons1 = compare_scholarships(target_same_url, cand)
        self.assertGreaterEqual(score1, 0.95)
        self.assertTrue(any("رابط التقديم" in r for r in reasons1))

        # Target 2: Conflicting country penalty
        target_diff_country = {
            "title": "منحة دراسية سنوية 2026",
            "country": "المملكة المتحدة",
            "organization_name": "جامعة أخرى",
            "apply_link": "https://uk-scholarship.example.org",
        }
        score2, _ = compare_scholarships(target_diff_country, cand)
        self.assertLess(score2, 0.50)


class AdminDuplicateDetectionEndpointTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        self.addCleanup(self.engine.dispose)
        from sqlalchemy import text

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE scholarships ("
                    "id INTEGER PRIMARY KEY, "
                    "title TEXT NOT NULL, "
                    "slug TEXT, "
                    "organization_name TEXT, "
                    "country TEXT, "
                    "deadline DATE, "
                    "no_deadline BOOLEAN DEFAULT 0, "
                    "image_url TEXT, "
                    "description_html TEXT, "
                    "apply_link TEXT, "
                    "apply_email TEXT, "
                    "apply_phone TEXT, "
                    "pdf_url TEXT, "
                    "attachments JSON, "
                    "is_extension BOOLEAN DEFAULT 0, "
                    "source TEXT NOT NULL, "
                    "source_id TEXT, "
                    "source_url TEXT, "
                    "study_level TEXT, "
                    "funding_type TEXT, "
                    "majors JSON, "
                    "required_documents JSON, "
                    "status TEXT DEFAULT 'pending', "
                    "scraped_at TIMESTAMP, "
                    "reviewed_at TIMESTAMP, "
                    "reviewed_by TEXT, "
                    "updated_at TIMESTAMP"
                    ")"
                )
            )
        User.__table__.create(self.engine)

        self.session_factory = sessionmaker(bind=self.engine)
        with self.session_factory() as db:
            # Create admin user
            admin_user = User(
                full_name="م. خالد النجار",
                email="admin@scholarai.com",
                hashed_password="mock-hashed-password",
                role="admin",
            )
            student_user = User(
                full_name="طالب مجتهد",
                email="student@scholarai.com",
                hashed_password="mock-hashed-password",
                role="student",
            )
            db.add_all([admin_user, student_user])
            db.flush()

            self.admin_token = create_access_token({"sub": str(admin_user.id)})
            self.student_token = create_access_token({"sub": str(student_user.id)})

            # Seed existing scholarships
            s1 = Scholarship(
                id=1,
                title="منحة إسطنبول التقنية الممولة بالكامل",
                organization_name="جامعة إسطنبول التقنية",
                country="تركيا",
                deadline=date(2026, 12, 1),
                apply_link="https://itu.edu.tr/scholarship/apply",
                source="for9a",
                source_id="for9a-101",
                status="approved",
                scraped_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            )
            s2 = Scholarship(
                id=2,
                title="منحة تشيفنينغ البريطانية للدراسات العليا",
                organization_name="الحكومة البريطانية",
                country="بريطانيا",
                deadline=date(2026, 11, 1),
                apply_link="https://chevening.org/apply",
                source="ministry",
                source_id="min-202",
                status="approved",
                scraped_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
            )
            s3 = Scholarship(
                id=3,
                title="منحة جامعة إسطنبول التقنية 2026",
                organization_name="جامعة إسطنبول التقنية",
                country="تركيا",
                deadline=date(2026, 12, 1),
                apply_link="https://itu.edu.tr/scholarship/apply?ref=ministry",
                source="ministry",
                source_id="min-303",
                status="pending",
                scraped_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
            )
            db.add_all([s1, s2, s3])
            db.commit()

        def override_get_db():
            with self.session_factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_get_db
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def test_get_scholarship_duplicates_for_existing(self):
        # Scholarship 3 is a duplicate of Scholarship 1
        response = self.client.get(
            "/admin/scholarships/3/duplicates",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["is_suspected_duplicate"])
        self.assertGreaterEqual(data["highest_similarity_score"], 0.90)
        self.assertGreater(len(data["candidates"]), 0)

        top_match = data["candidates"][0]
        self.assertEqual(top_match["id"], 1)
        self.assertIn("جامعة إسطنبول التقنية", top_match["organization_name"])
        self.assertGreater(len(top_match["reasons"]), 0)

    def test_get_scholarship_duplicates_not_found(self):
        response = self.client.get(
            "/admin/scholarships/999/duplicates",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 404)

    def test_check_scholarship_duplicate_post_payload(self):
        payload = {
            "title": "منحة تشيفنينغ للدراسة في بريطانيا 2026",
            "country": "بريطانيا",
            "organization_name": "الحكومة البريطانية",
            "apply_link": "https://chevening.org/apply?utm_campaign=winter",
        }
        response = self.client.post(
            "/admin/scholarships/check-duplicate",
            json=payload,
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["is_suspected_duplicate"])
        self.assertGreaterEqual(data["highest_similarity_score"], 0.90)
        self.assertEqual(data["candidates"][0]["id"], 2)

    def test_authorization_restrictions(self):
        # Unauthorized without token
        res_no_auth = self.client.get("/admin/scholarships/1/duplicates")
        self.assertEqual(res_no_auth.status_code, 401)

        # Forbidden for student role
        res_forbidden = self.client.get(
            "/admin/scholarships/1/duplicates",
            headers={"Authorization": f"Bearer {self.student_token}"},
        )
        self.assertEqual(res_forbidden.status_code, 403)


if __name__ == "__main__":
    unittest.main()
