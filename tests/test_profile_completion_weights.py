import unittest
from datetime import date

from app.schemas.profile import (
    AcademicInfo,
    AcademicLevel,
    DesiredDegreeLevel,
    Documents,
    Experience,
    ExperienceResponse,
    ExperienceType,
    FieldOfStudy,
    FinancialStatus,
    FundingType,
    Gender,
    GPA,
    GPAScale,
    LanguageItem,
    LanguageProficiency,
    PersonalInfo,
    PreferencesResponse,
    SkillsAndLanguages,
    UploadedFile,
    UploadStatus,
    calculate_profile_completion,
)


class ProfileCompletionWeightsTests(unittest.TestCase):
    def test_personal_information_scoring_max_22_percent(self):
        # Empty personal info gives 0%
        self.assertEqual(
            calculate_profile_completion(
                personal_info=None,
                academic_info=None,
                documents=Documents(),
                skills_and_languages=SkillsAndLanguages(),
                experiences=[],
                preferences=PreferencesResponse(),
            ),
            0.0,
        )

        # Partial personal info: first_name (1%) + last_name (1%) + birth_date (4%) = 6%
        partial_personal = PersonalInfo(
            first_name="Sara",
            last_name="Ahmad",
            email="sara@example.com",
            birth_date=date(2000, 1, 1),
            gender=Gender.FEMALE,
            nationality="PS",
            country_of_residence="JO",
            financial_status=FinancialStatus.LIMITED,
            passport_number="A12345678",
        )
        # All personal fields filled:
        # First name (1%) + Last name (1%) + Birth date (4%) + Nationality (5%) +
        # Country of residence (4%) + Gender (1%) + Financial status (2%) + Passport (4%) = 22%
        score = calculate_profile_completion(
            personal_info=partial_personal,
            academic_info=None,
            documents=Documents(),
            skills_and_languages=SkillsAndLanguages(),
            experiences=[],
            preferences=PreferencesResponse(),
        )
        self.assertEqual(score, 22.0)

    def test_academic_information_scoring_max_22_percent(self):
        # academic_level (6%) + field_of_study (6%) + gpa (7%) + expected_graduation_year (3%) = 22%
        academic = AcademicInfo(
            academic_level=AcademicLevel.BACHELOR,
            field_of_study=FieldOfStudy.COMPUTER_SCIENCE,
            gpa=GPA(value=3.9, scale=GPAScale.SCALE_4),
            expected_graduation_year=2026,
            institution=None,  # optional, does not affect 22%
        )
        score = calculate_profile_completion(
            personal_info=None,
            academic_info=academic,
            documents=Documents(),
            skills_and_languages=SkillsAndLanguages(),
            experiences=[],
            preferences=PreferencesResponse(),
        )
        self.assertEqual(score, 22.0)

    def test_scholarship_preferences_scoring_max_28_percent(self):
        # Target degree (8%) + Target field (8%) + Preferred countries (6%) + Funding preference (6%) = 28%
        preferences = PreferencesResponse(
            desired_degree_level=DesiredDegreeLevel.MASTER,
            funding_type=FundingType.FULL,
            preferred_fields_of_study=["AI", "Data Science"],
            preferred_countries=["TR", "MY"],
            open_to_all_countries=False,
        )
        score = calculate_profile_completion(
            personal_info=None,
            academic_info=None,
            documents=Documents(),
            skills_and_languages=SkillsAndLanguages(),
            experiences=[],
            preferences=preferences,
        )
        self.assertEqual(score, 28.0)

        # Open to all countries option also awards the 6%
        preferences_open = PreferencesResponse(
            desired_degree_level=DesiredDegreeLevel.MASTER,
            funding_type=FundingType.FULL,
            preferred_fields_of_study=["AI"],
            preferred_countries=[],
            open_to_all_countries=True,
        )
        score_open = calculate_profile_completion(
            personal_info=None,
            academic_info=None,
            documents=Documents(),
            skills_and_languages=SkillsAndLanguages(),
            experiences=[],
            preferences=preferences_open,
        )
        self.assertEqual(score_open, 28.0)

    def test_languages_scoring_max_10_percent(self):
        # English proficiency only (7%)
        skills_langs_eng = SkillsAndLanguages(
            languages=[LanguageItem(name="English", proficiency=LanguageProficiency.ADVANCED)]
        )
        score_eng = calculate_profile_completion(
            personal_info=None,
            academic_info=None,
            documents=Documents(),
            skills_and_languages=skills_langs_eng,
            experiences=[],
            preferences=PreferencesResponse(),
        )
        self.assertEqual(score_eng, 7.0)

        # English certificate uploaded awards the 7% for English proficiency
        docs_with_test = Documents(
            english_test=UploadedFile(status=UploadStatus.UPLOADED, file_name="ielts.pdf")
        )
        score_cert = calculate_profile_completion(
            personal_info=None,
            academic_info=None,
            documents=docs_with_test,
            skills_and_languages=SkillsAndLanguages(),
            experiences=[],
            preferences=PreferencesResponse(),
        )
        # Note: english_test is both language proficiency (7%) and Language certificate document (3%)
        # 7% (languages) + 3% (documents) = 10.0%
        self.assertEqual(score_cert, 10.0)

        # English (7%) + Other language (Arabic) (3%) = 10%
        skills_langs_both = SkillsAndLanguages(
            languages=[
                LanguageItem(name="English", proficiency=LanguageProficiency.ADVANCED),
                LanguageItem(name="العربية", proficiency=LanguageProficiency.NATIVE),
            ]
        )
        score_both = calculate_profile_completion(
            personal_info=None,
            academic_info=None,
            documents=Documents(),
            skills_and_languages=skills_langs_both,
            experiences=[],
            preferences=PreferencesResponse(),
        )
        self.assertEqual(score_both, 10.0)

    def test_experience_scoring_max_5_percent(self):
        # Answer is No -> section complete (5%)
        score_no = calculate_profile_completion(
            personal_info=None,
            academic_info=None,
            documents=Documents(),
            skills_and_languages=SkillsAndLanguages(),
            experiences=[],
            preferences=PreferencesResponse(),
            has_experience=False,
        )
        self.assertEqual(score_no, 5.0)

        # Answer is Yes but 0 experiences entered -> 0%
        score_yes_empty = calculate_profile_completion(
            personal_info=None,
            academic_info=None,
            documents=Documents(),
            skills_and_languages=SkillsAndLanguages(),
            experiences=[],
            preferences=PreferencesResponse(),
            has_experience=True,
        )
        self.assertEqual(score_yes_empty, 0.0)

        # Answer is Yes and at least 1 valid experience -> 5%
        valid_exp = ExperienceResponse(
            id=1,
            experience_type=ExperienceType.WORK,
            title="Engineer",
            organization="Google",
            start_date=date(2023, 1, 1),
            is_current=True,
        )
        score_yes_with_exp = calculate_profile_completion(
            personal_info=None,
            academic_info=None,
            documents=Documents(),
            skills_and_languages=SkillsAndLanguages(),
            experiences=[valid_exp],
            preferences=PreferencesResponse(),
            has_experience=True,
        )
        self.assertEqual(score_yes_with_exp, 5.0)

    def test_skills_progressive_scoring_max_5_percent(self):
        def score_for_skills(skills_list):
            return calculate_profile_completion(
                personal_info=None,
                academic_info=None,
                documents=Documents(),
                skills_and_languages=SkillsAndLanguages(skills=skills_list),
                experiences=[],
                preferences=PreferencesResponse(),
            )

        self.assertEqual(score_for_skills([]), 0.0)
        self.assertEqual(score_for_skills(["Python"]), 2.0)
        self.assertEqual(score_for_skills(["Python", "SQL"]), 4.0)
        self.assertEqual(score_for_skills(["Python", "SQL", "Docker"]), 5.0)
        self.assertEqual(score_for_skills(["Python", "SQL", "Docker", "Git"]), 5.0)

    def test_documents_scoring_max_8_percent(self):
        # CV (2%) + Motivation letter (2%) + Language cert (3%) + Degree cert (1%) = 8%
        docs = Documents(
            cv=UploadedFile(status=UploadStatus.UPLOADED),
            motivation_letter=UploadedFile(status=UploadStatus.UPLOADED),
            english_test=UploadedFile(status=UploadStatus.UPLOADED),
            graduation_certificate=UploadedFile(status=UploadStatus.UPLOADED),
        )
        # Note: english_test uploaded also counts towards English proficiency (7%)
        # Documents alone = 2 + 2 + 3 + 1 = 8%. Plus english_test gives 7% language proficiency -> total 15%
        score = calculate_profile_completion(
            personal_info=None,
            academic_info=None,
            documents=docs,
            skills_and_languages=SkillsAndLanguages(),
            experiences=[],
            preferences=PreferencesResponse(),
        )
        self.assertEqual(score, 15.0)  # 8% docs + 7% english proficiency

    def test_fully_completed_profile_reaches_exact_100_percent(self):
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
        academic = AcademicInfo(
            academic_level=AcademicLevel.BACHELOR,
            field_of_study=FieldOfStudy.COMPUTER_SCIENCE,
            gpa=GPA(value=3.9, scale=GPAScale.SCALE_4),
            expected_graduation_year=2026,
        )  # 22%
        preferences = PreferencesResponse(
            desired_degree_level=DesiredDegreeLevel.MASTER,
            funding_type=FundingType.FULL,
            preferred_fields_of_study=["Computer Science"],
            preferred_countries=["DE"],
        )  # 28%
        skills_langs = SkillsAndLanguages(
            languages=[
                LanguageItem(name="English", proficiency=LanguageProficiency.ADVANCED),
                LanguageItem(name="العربية", proficiency=LanguageProficiency.NATIVE),
            ],  # 10%
            skills=["Python", "FastAPI", "PostgreSQL"],  # 5%
        )
        experiences = [
            ExperienceResponse(
                id=1,
                experience_type=ExperienceType.WORK,
                title="Software Engineer",
                organization="Tech",
                start_date=date(2023, 1, 1),
                is_current=True,
            )
        ]  # 5%
        docs = Documents(
            cv=UploadedFile(status=UploadStatus.UPLOADED),
            motivation_letter=UploadedFile(status=UploadStatus.UPLOADED),
            english_test=UploadedFile(status=UploadStatus.UPLOADED),
            graduation_certificate=UploadedFile(status=UploadStatus.UPLOADED),
        )  # 8%

        total_score = calculate_profile_completion(
            personal_info=personal,
            academic_info=academic,
            documents=docs,
            skills_and_languages=skills_langs,
            experiences=experiences,
            preferences=preferences,
            has_experience=True,
        )
        self.assertEqual(total_score, 100.0)


if __name__ == "__main__":
    unittest.main()
