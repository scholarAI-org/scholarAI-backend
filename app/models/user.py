from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from app.core.database import Base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

class User(Base):
    
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="student")  # 'student' أو 'admin'
    is_active = Column(Boolean, default=True)
    is_email_verified = Column(Boolean, default=False, nullable=False)
    email_verification_otp_hash = Column(String(64), nullable=True)
    email_verification_otp_expires_at = Column(DateTime, nullable=True)
    email_verification_otp_sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    profile = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")
