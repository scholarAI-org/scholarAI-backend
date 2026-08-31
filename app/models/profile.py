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
    DateTime,
    func,
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

    # Personal Info
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    birth_date = Column(Date, nullable=False)
    gender = Column(Enum(Gender), nullable=False)
    nationality = Column(String(2), nullable=False)  # ISO 2-letter
    country_of_residence = Column(String(2), nullable=False)  # ISO 2-letter
    phone_number = Column(String(20), nullable=True)
    city = Column(String(100), nullable=True)
    financial_status = Column(Enum(FinancialStatus), nullable=True)
    id_number = Column(String(9), nullable=True)
    passport_number = Column(String(20), nullable=True)

    # Academic Info
    academic_level = Column(Enum(AcademicLevel), nullable=False)
    field_of_study = Column(Enum(FieldOfStudy), nullable=False)
    institution = Column(String(255), nullable=False)
    gpa_value = Column(Float, nullable=False)
    gpa_scale = Column(Enum(GPAScale), nullable=False)
    current_study_language = Column(JSON, default=list)  # List[str]
    expected_graduation_year = Column(Integer, nullable=True)

    # Documents (JSON Object matching Documents schema)
    documents = Column(JSON, default=dict)

    # Skills and Languages (JSON Object matching SkillsAndLanguages schema)
    languages_data = Column(JSON, default=list)
    skills_data = Column(JSON, default=list)

    desired_degree_level = Column(Enum(DesiredDegreeLevel), nullable=True)
    funding_type = Column(Enum(FundingType), nullable=True)
    preferred_fields_of_study = Column(JSON, default=list)
    preferred_countries = Column(JSON, default=list)
    is_completed = Column(Boolean, default=False)


    # Meta
    profile_completion_percentage = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

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