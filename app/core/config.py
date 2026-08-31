from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # إعدادات قاعدة البيانات والتطبيق
PROJECT_NAME: str = "Scholar AI"
    DATABASE_URL: str = "sqlite:///./scholar_ai.db"
    SECRET_KEY: str = "scholar_ai_super_secret_key_change_me_later"
    ALGORITHM: str = "HS256"
    
    # إعدادات الواجهة الأمامية
    FRONTEND_URL: str = "http://localhost:3000"
    
    # إعدادات البريد الإلكتروني
    MAIL_USERNAME: Optional[str] = None
    MAIL_PASSWORD: Optional[str] = None
    MAIL_FROM: Optional[str] = None
    MAIL_PORT: Optional[int] = 587
    MAIL_SERVER: Optional[str] = "smtp.gmail.com"
    MAIL_FROM_NAME: Optional[str] = "Scholar AI Support"

    RESEND_API_KEY: Optional[str] = None
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
