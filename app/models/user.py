from enum import Enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.core.database import Base

class UserRole(str, Enum):
    STUDENT = "student"
    ADMIN = "admin"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)        # الاسم (مطلوب)
    email = Column(String, unique=True, index=True, nullable=False) # البريد
    hashed_password = Column(String, nullable=False)  # كلمة المرور المشفرة
    role = Column(String, default=UserRole.STUDENT)   # الدور (الافتراضي طالب)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())