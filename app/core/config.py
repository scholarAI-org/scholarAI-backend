from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # إعدادات قاعدة البيانات والتطبيق
    PROJECT_NAME: str = "ascv"
    DATABASE_URL: str = "postgresql://postgres:123456@localhost:5432/scholarai_db"
    DATABASE_URL_UNPOOLED: Optional[str] = None
    SECRET_KEY: str = "scholar_ai_super_secret_key_change_me_later"
    ALGORITHM: str = "HS256"
    
    # إعدادات الواجهة الأمامية
    FRONTEND_URL: str = "http://localhost:3000"
    
    # إعدادات البريد الإلكتروني
    MAIL_USERNAME: Optional[str] = "test@example.com"
    MAIL_PASSWORD: Optional[str] = "password"
    # RESEND_FROM_EMAIL is preferred. MAIL_FROM remains a legacy alias.
    RESEND_FROM_EMAIL: Optional[str] = None
    MAIL_FROM: Optional[str] = None
    MAIL_PORT: Optional[int] = 587
    MAIL_SERVER: Optional[str] = "smtp.gmail.com"
    MAIL_FROM_NAME: Optional[str] = "Scholar AI Support"

    RESEND_API_KEY: str = ""
    EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES: int = 10
    EMAIL_VERIFICATION_OTP_RESEND_COOLDOWN_SECONDS: int = 60
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
