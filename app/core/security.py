from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
import jwt
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.models.user import User

# إعداد محرك تشفير الباسورد باستخدام Bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# دالة لتشفير كلمة المرور
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# دالة للتحقق من مطابقة الباسورد عند تسجيل الدخول
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# إعدادات الـ JWT — تُقرأ من .env عبر settings
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # التوكن ينتهي بعد 24 ساعة


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# دالة لتوليد توكن إعادة التعيين ينتهي بعد 15 دقيقة
def create_reset_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode = {"sub": email, "type": "reset"}
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# دالة للتحقق من صحة توكن إعادة التعيين
def verify_reset_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "reset":
            return None
        return payload.get("sub")  # يعيد البريد الإلكتروني
    except jwt.PyJWTError:
        return None


# ==========================================
# استخراج JWT من الـ cookie أولاً، ثم Bearer header كـ fallback
# ==========================================

def _decode_token(token: str) -> dict:
    """
    Decode and validate a JWT string.
    Raises HTTPException 401 on any failure.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="غير مصرح، التوكن غير صالح أو منتهي الصلاحية",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        return payload
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise credentials_exception from exc


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """
    Resolve the authenticated user from:
      1. HttpOnly cookie  (primary — browser clients after login)
      2. Authorization: Bearer <token>  (fallback — direct API / test clients)

    Raises HTTP 401 if neither is present or the token is invalid/expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="غير مصرح، التوكن غير صالح أو منتهي الصلاحية",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # ── 1. Cookie (HttpOnly, set by /auth/login or /auth/google) ──────────
    token: Optional[str] = request.cookies.get(settings.COOKIE_NAME)

    # ── 2. Bearer header fallback (API clients, automated tests) ─────────
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise credentials_exception

    payload = _decode_token(token)

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    return user
