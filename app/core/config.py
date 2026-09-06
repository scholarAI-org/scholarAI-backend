from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # إعدادات قاعدة البيانات والتطبيق
    PROJECT_NAME: str = "ascv"
    DATABASE_URL: str = "postgresql://postgres:123456@localhost:5432/scholarai_db"
    SECRET_KEY: str = "scholar_ai_super_secret_key_change_me_later"
    ALGORITHM: str = "HS256"

    # إعدادات الواجهة الأمامية
    FRONTEND_URL: str = "http://localhost:3000"

    # إعدادات البريد الإلكتروني
    MAIL_USERNAME: Optional[str] = "test@example.com"
    MAIL_PASSWORD: Optional[str] = "password"
    RESEND_FROM_EMAIL: Optional[str] = None
    MAIL_FROM: Optional[str] = "test@example.com"
    MAIL_PORT: Optional[int] = 587
    MAIL_SERVER: Optional[str] = "smtp.gmail.com"
    MAIL_FROM_NAME: Optional[str] = "Scholar AI Support"

    RESEND_API_KEY: Optional[str] = None

    EMAIL_VERIFICATION_ENABLED: bool = False
    EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES: int = 10
    EMAIL_VERIFICATION_OTP_RESEND_COOLDOWN_SECONDS: int = 60

    # Object storage (private S3-compatible bucket)
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_S3_BUCKET: str = "scholarai-documents"
    AWS_S3_ENDPOINT_URL: Optional[str] = None
    S3_PRESIGN_PUT_EXPIRE_SECONDS: int = 300
    S3_PRESIGN_GET_EXPIRE_SECONDS: int = 120
    S3_MAX_FILE_BYTES: int = 10 * 1024 * 1024
    S3_MAX_AVATAR_BYTES: int = 5 * 1024 * 1024
    S3_MAX_RECOMMENDATION_LETTERS: int = 3


settings = Settings()
