import unittest
from datetime import date

from pydantic import ValidationError

from app.schemas.profile import (
    GPA,
    AcademicInfoUpdate,
    AcademicLevel,
    DesiredDegreeLevel,
    Documents,
    Experience,
    ExperienceType,
    FinancialStatus,
    FundingType,
    Gender,
    GPAScale,
    LanguageItem,
    LanguageProficiency,
    PersonalInfo,
    Preferences,
    PreferencesResponse,
    SkillsAndLanguages,
    UploadedFile,
    UploadStatus,
    calculate_profile_completion,
)


class ProfileFieldRequirementsTests(unittest.TestCase):
    def test_personal_info_requires_financial_status(self):
        # Missing financial_status should fail
        with self.assertRaises(ValidationError) as ctx:
            PersonalInfo(
                first_name="Ahmad",
                last_name="Ali",
                email="ahmad@example.com",
                birth_date=date(2000, 1, 1),
                gender=Gender.MALE,
                nationality="PS",
                country_of_residence="PS",
            )
        errors = ctx.exception.errors()
        self.assertTrue(any(err["loc"] == ("financial_status",) for err in errors))

        # Providing valid financial_status succeeds
        info = PersonalInfo(
            first_name="Ahmad",
            last_name="Ali",
            email="ahmad@example.com",
            birth_date=date(2000, 1, 1),
            gender=Gender.MALE,
            nationality="PS",
            country_of_residence="PS",
            financial_status=FinancialStatus.LIMITED,
        )
        self.assertEqual(info.financial_status, FinancialStatus.LIMITED)

    def test_academic_info_gpa_and_expected_graduation_year_required_institution_optional(
        self,
    ):
        # Institution omitted -> Should succeed
        academic = AcademicInfoUpdate(
            academic_level=AcademicLevel.BACHELOR,
            field_of_study="Computer Science",
            field_of_study_openalex_id="https://openalex.org/subfields/1702",
            study_status="CURRENTLY_STUDYING",
            gpa=GPA(value=3.8, scale=GPAScale.SCALE_4),
            expected_graduation_year=2026,
        )
        self.assertIsNone(academic.institution)
        self.assertEqual(academic.expected_graduation_year, 2026)
        self.assertEqual(academic.gpa.value, 3.8)

        # Missing GPA -> Should fail
        with self.assertRaises(ValidationError) as ctx:
            AcademicInfoUpdate(
                academic_level=AcademicLevel.BACHELOR,
                field_of_study="Computer Science",
                field_of_study_openalex_id="https://openalex.org/subfields/1702",
                study_status="CURRENTLY_STUDYING",
                expected_graduation_year=2026,
            )
        self.assertTrue(any(err["loc"] == ("gpa",) for err in ctx.exception.errors()))

        # Missing expected_graduation_year -> Should fail
        with self.assertRaises(ValidationError) as ctx:
            AcademicInfoUpdate(
                academic_level=AcademicLevel.BACHELOR,
                field_of_study="Computer Science",
                field_of_study_openalex_id="https://openalex.org/subfields/1702",
                study_status="CURRENTLY_STUDYING",
                gpa=GPA(value=3.5, scale=GPAScale.SCALE_4),
            )
        self.assertTrue(
            any(
                err["loc"] == ("expected_graduation_year",)
                for err in ctx.exception.errors()
            )
        )

    def test_experience_requires_all_except_description(self):
        # Valid non-current experience with end_date and no description
        exp = Experience(
            experience_type=ExperienceType.WORK,
            title="Software Developer",
            organization="Tech Co",
            start_date=date(2023, 1, 1),
            end_date=date(2024, 1, 1),
            is_current=False,
        )
        self.assertIsNone(exp.description)
        self.assertFalse(exp.is_current)

        # Non-current experience without end_date -> Should fail
        with self.assertRaises(ValidationError) as ctx:
            Experience(
                experience_type=ExperienceType.WORK,
                title="Software Developer",
                organization="Tech Co",
                start_date=date(2023, 1, 1),
                is_current=False,
            )
        self.assertIn("تاريخ النهاية إجباري", str(ctx.exception))

        # Current experience with is_current=True and no end_date -> Should succeed
        current_exp = Experience(
            experience_type=ExperienceType.VOLUNTEER,
            title="Volunteer",
            organization="Charity Org",
            start_date=date(2023, 6, 1),
            is_current=True,
        )
        self.assertTrue(current_exp.is_current)
        self.assertIsNone(current_exp.end_date)
        self.assertIsNone(current_exp.description)

        # Missing required field (e.g. organization) -> Should fail
        with self.assertRaises(ValidationError):
            Experience(
                experience_type=ExperienceType.WORK,
                title="Software Developer",
                start_date=date(2023, 1, 1),
                end_date=date(2024, 1, 1),
            )

    def test_preferences_preferred_countries_is_optional(self):
        # Omitted preferred_countries -> Should default to empty list
        pref1 = Preferences(
            desired_degree_level=DesiredDegreeLevel.MASTER,
            funding_type=FundingType.FULL,
        )
        self.assertEqual(pref1.preferred_countries, [])

        # preferred_countries=None -> Should accept and default to empty list
        pref2 = Preferences(
            desired_degree_level=DesiredDegreeLevel.MASTER,
            funding_type=FundingType.FULL,
            preferred_countries=None,
        )
        self.assertEqual(pref2.preferred_countries, [])

        # Explicit preferred_countries
        pref3 = Preferences(
            desired_degree_level=DesiredDegreeLevel.MASTER,
            funding_type=FundingType.FULL,
            preferred_countries=["TR", "DE"],
        )
        self.assertEqual(pref3.preferred_countries, ["TR", "DE"])

    def test_calculate_profile_completion_logic(self):
        personal = PersonalInfo(
            first_name="Ahmad",
            last_name="Ali",
            email="ahmad@example.com",
            birth_date=date(2000, 1, 1),
            gender=Gender.MALE,
            nationality="PS",
            country_of_residence="PS",
            financial_status=FinancialStatus.MODERATE,
            passport_number="P12345678",
        )  # 22%
        academic = AcademicInfoUpdate(
            academic_level=AcademicLevel.BACHELOR,
            field_of_study="Computer Science",
            field_of_study_openalex_id="https://openalex.org/subfields/1702",
            study_status="CURRENTLY_STUDYING",
            gpa=GPA(value=85.0, scale=GPAScale.SCALE_100),
            expected_graduation_year=2027,
            # institution is omitted/optional!
        )  # 22%
        preferences = PreferencesResponse(
            desired_degree_level=DesiredDegreeLevel.MASTER,
            funding_type=FundingType.FULL,
            target_field_of_study="Engineering",
            preferred_countries=["DE"],
        )  # 28%
        docs = Documents(
            cv=UploadedFile(status=UploadStatus.UPLOADED),
            motivation_letter=UploadedFile(status=UploadStatus.UPLOADED),
            english_test=UploadedFile(status=UploadStatus.UPLOADED),
            graduation_certificate=UploadedFile(status=UploadStatus.UPLOADED),
        )  # 8%
        skills = SkillsAndLanguages(
            languages=[
                LanguageItem(name="English", proficiency=LanguageProficiency.ADVANCED),
                LanguageItem(name="العربية", proficiency=LanguageProficiency.NATIVE),
            ],  # 10%
            skills=["Python", "CAD", "MATLAB"],  # 5%
        )

        score = calculate_profile_completion(
            personal_info=personal,
            academic_info=academic,
            documents=docs,
            skills_and_languages=skills,
            experiences=[],
            preferences=preferences,
            has_experience=False,  # 5%
        )
        # All sections complete = 100%
        self.assertEqual(score, 100.0)


if __name__ == "__main__":
    unittest.main()
