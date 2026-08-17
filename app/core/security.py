from passlib.context import CryptContext
from datetime import datetime, timedelta
import jwt
from typing import Optional

# ➕ إضافة الاستيرادات الخاصة بـ FastAPI و Database من أجل دالة get_current_user
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User

# إعداد محرك تشفير الباسورد باستخدام Bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# دالة لتشفير كلمة المرور
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# دالة للتحقق من مطابقة الباسورد عند تسجيل الدخول مستقبلاً
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# إعدادات الـ JWT (في المشاريع الحقيقية توضع هذه القيم في ملف .env)
SECRET_KEY = "scholar_ai_super_secret_key_change_me_later"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # التوكن ينتهي بعد 24 ساعة

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# دالة لتوليد توكن إعادة التعيين ينتهي بعد 15 دقيقة
def create_reset_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=15)
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
# 🆕 الدالة الجديدة: استخراج المستخدم الحالي من التوكن
# ==========================================

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="غير مصرح، التوكن غير صالح أو منتهي الصلاحية",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id_str = payload.get("sub")

        if user_id_str is None:
            raise credentials_exception

        user_id = int(user_id_str)

    except (jwt.PyJWTError, ValueError, TypeError):
        raise credentials_exception

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if user is None:
        raise credentials_exception

    return user
# 