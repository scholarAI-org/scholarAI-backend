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
    created_at = Column(DateTime, default=datetime.utcnow)
    profile = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")
