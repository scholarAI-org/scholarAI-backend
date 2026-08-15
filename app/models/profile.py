from sqlalchemy import Column, ForeignKey, Integer, String

from app.core.database import Base


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Personal Information
    full_name = Column(String, nullable=False)
    gender = Column(String, nullable=True)
    marital_status = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    country_of_birth = Column(String, nullable=True)
    nationality = Column(String, nullable=True)
    country_of_residence = Column(String, nullable=True)
    id_type = Column(String, nullable=True)
    id_number = Column(String, nullable=True)

    # Family & Financial Information
    father_name = Column(String, nullable=True)
    mother_name = Column(String, nullable=True)
    father_income = Column(Float, default=0.0)
    mother_income = Column(Float, default=0.0)
    num_of_siblings = Column(Integer, default=0)
    currency = Column(String, default="USD")

    # Contact Information
    country = Column(String, nullable=True)
    city = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    phone_number = Column(String, nullable=True)

    # Academic Background
    degree = Column(String, nullable=True)
    major = Column(String, nullable=True)
    institution_name = Column(String, nullable=True)
    graduation_year = Column(Integer, nullable=True)
    gpa = Column(Float, nullable=True)
    gpa_scale = Column(String, default="100")

    # Relationships
    user = relationship("User", back_populates="profile")
    experiences = relationship("WorkExperience", back_populates="profile", cascade="all, delete-orphan")
    languages = relationship("LanguageDetail", back_populates="profile", cascade="all, delete-orphan")


class WorkExperience(Base):
    __tablename__ = "work_experiences"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    
    company_name = Column(String, nullable=False)
    role_title = Column(String, nullable=True)
    employment_type = Column(String, nullable=True)
    location = Column(String, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    is_current = Column(Boolean, default=False)

    profile = relationship("Profile", back_populates="experiences")


class LanguageDetail(Base):
    __tablename__ = "language_details"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)

    language_name = Column(String, nullable=False)
    proficiency_level = Column(String, nullable=True)
    certificate_url = Column(String, nullable=True)

    profile = relationship("Profile", back_populates="languages")
