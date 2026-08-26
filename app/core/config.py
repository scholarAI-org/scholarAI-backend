from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # إعدادات قاعدة البيانات والتطبيق
    PROJECT_NAME: str = "ascv"
    DATABASE_URL: str = "sqlite:///./scholar_ai.db"  # قيمة افتراضية تمنع الأيرور
    SECRET_KEY: str = "scholar_ai_super_secret_key_change_me_later"
    ALGORITHM: str = "HS256"
    
    # إعدادات الواجهة الأمامية
    FRONTEND_URL: str = "http://localhost:3000"
    
    # إعدادات البريد الإلكتروني
    MAIL_USERNAME: Optional[str] = "test@example.com"
    MAIL_PASSWORD: Optional[str] = "password"
    MAIL_FROM: Optional[str] = "test@example.com"
    MAIL_PORT: Optional[int] = 587
    MAIL_SERVER: Optional[str] = "smtp.gmail.com"
    MAIL_FROM_NAME: Optional[str] = "Scholar AI Support"

    RESEND_API_KEY: str = "" 
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
