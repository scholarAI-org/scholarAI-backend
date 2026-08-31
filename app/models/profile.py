import enum

from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    Column,
    Date,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Gender(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"


class FinancialStatus(str, enum.Enum):
    LIMITED = "LIMITED"
    MODERATE = "MODERATE"
    STABLE = "STABLE"


class AcademicLevel(str, enum.Enum):
    TAWJIHI = "TAWJIHI"  # توجيهي / ثانوية عامة
    BACHELOR = "BACHELOR"
    MASTER = "MASTER"
    PHD = "PHD"


class FieldOfStudy(str, enum.Enum):
    # فروع التوجيهي
    SCIENTIFIC = "SCIENTIFIC"
    LITERARY = "LITERARY"
    SHARIA = "SHARIA"
    INDUSTRIAL = "INDUSTRIAL"
    ENTREPRENEURSHIP_BUSINESS = "ENTREPRENEURSHIP_BUSINESS"
    AGRICULTURAL = "AGRICULTURAL"
    HOME_ECONOMICS = "HOME_ECONOMICS"

    # التخصصات الجامعية
    ENGINEERING = "ENGINEERING"
    COMPUTER_SCIENCE = "COMPUTER_SCIENCE"
    MEDICINE = "MEDICINE"
    BUSINESS = "BUSINESS"
    ARTS = "ARTS"
    OTHER = "OTHER"


class GPAScale(str, enum.Enum):
    SCALE_4 = "SCALE_4"
    SCALE_5 = "SCALE_5"
    SCALE_10 = "SCALE_10"
    SCALE_100 = "SCALE_100"


class DesiredDegreeLevel(str, enum.Enum):
    BACHELOR = "BACHELOR"
    MASTER = "MASTER"
    PHD = "PHD"
    DIPLOMA = "DIPLOMA"
    OTHER = "OTHER"


class FundingType(str, enum.Enum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    SELF = "SELF"
    ANY = "ANY"


class ExperienceType(str, enum.Enum):
    WORK = "WORK"
    VOLUNTEER = "VOLUNTEER"
    RESEARCH = "RESEARCH"
    STUDENT_ACTIVITY = "STUDENT_ACTIVITY"


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    first_name = Column(String(50), nullable=True)
    last_name = Column(String(50), nullable=True)
    phone_number = Column(String(30), nullable=True)
    gender = Column(Enum(Gender), nullable=True)
    birth_date = Column(Date, nullable=True)
    nationality = Column(String(2), nullable=True)
    country_of_residence = Column(String(2), nullable=True)
    city = Column(String(100), nullable=True)
    financial_status = Column(Enum(FinancialStatus), nullable=True)
    id_number = Column(String(50), nullable=True)
    passport_number = Column(String(50), nullable=True)

    # ضبط النوع ليكون Enum(FieldOfStudy) ليتوافق مع Pydantic والموديل
    field_of_study = Column(Enum(FieldOfStudy), nullable=True)
    academic_level = Column(Enum(AcademicLevel), nullable=True)
    gpa_value = Column(Float, nullable=True)
    gpa_scale = Column(Enum(GPAScale), nullable=True)
    institution = Column(String(255), nullable=True)
    current_study_language = Column(ARRAY(String), nullable=True)
    expected_graduation_year = Column(Integer, nullable=True)

    documents_data = Column(JSON, nullable=True)
    languages_data = Column(JSON, nullable=True)
    skills_data = Column(JSON, nullable=True)

    desired_degree_level = Column(Enum(DesiredDegreeLevel), nullable=True)
    funding_type = Column(Enum(FundingType), nullable=True)
    preferred_fields_of_study = Column(JSON, default=list)
    preferred_countries = Column(JSON, default=list)
    is_completed = Column(Boolean, default=False)

    user = relationship("User", back_populates="profile")
    experiences = relationship(
        "Experience", back_populates="profile", cascade="all, delete-orphan"
    )


class Experience(Base):
    __tablename__ = "experiences"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(
        Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    experience_type = Column(Enum(ExperienceType), nullable=False)
    title = Column(String(250), nullable=False)
    organization = Column(String(250), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    is_current = Column(Boolean, default=False)
    description = Column(Text, nullable=True)

    profile = relationship("Profile", back_populates="experiences")