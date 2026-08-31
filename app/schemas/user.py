from pydantic import BaseModel, EmailStr, field_validator , Field
from typing import Optional
import re

# مخطط البيانات التي سيرسلها المستخدم عند التسجيل

class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: Optional[str] = "student"  # اختياري والقيمة الافتراضية طالب

    # التحقق من شروط كلمة المرور
    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        # 1. التحقق من الطول (8 أحرف على الأقل)
        if len(v) < 8:
            raise ValueError('كلمة المرور يجب أن تكون 8 أحرف على الأقل')
        
        # 2. التحقق من وجود رقم واحد على الأقل
        if not re.search(r"\d", v):
            raise ValueError('كلمة المرور يجب أن تحتوي على رقم واحد على الأقل')
        
        # 3. التحقق من وجود رمز خاص على الأقل (مثل @, #, $, %, إلخ)
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError('كلمة المرور يجب أن تحتوي على رمز خاص واحد على الأقل (!@#$%^&*)')
        
        return v


# مخطط البيانات التي نرجعها للمستخدم كـ Response (بدون الباسورد!)
class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: str
    is_active: bool
    is_email_verified: bool

    class Config:
        from_attributes = True


# مخطط بيانات تسجيل الدخول
class UserLogin(BaseModel):
    email: EmailStr
    password: str


# مخطط الـ Token المرجعة بعد تسجيل الدخول
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

# مخطط طلب إرسال رمز إعادة التعيين
class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("كلمة المرور يجب أن تكون 8 أحرف على الأقل")

        if not re.search(r"\d", v):
            raise ValueError(
                "كلمة المرور يجب أن تحتوي على رقم واحد على الأقل"
            )

        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError(
                "كلمة المرور يجب أن تحتوي على رمز خاص واحد على الأقل (!@#$%^&*)"
            )

        return v

# مخطط إعادة تعيين كلمة المرور باستخدام الرمز
class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(
        ...,
        min_length=8,
        description="كلمة المرور الجديدة يجب ألا تقل عن 8 خانات"
    )

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('كلمة المرور يجب أن تكون 8 أحرف على الأقل')

        if not re.search(r"\d", v):
            raise ValueError('كلمة المرور يجب أن تحتوي على رقم واحد على الأقل')

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError(
                'كلمة المرور يجب أن تحتوي على رمز خاص واحد على الأقل (!@#$%^&*)'
            )

        return v


class MessageResponse(BaseModel):
    message: str


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., pattern=r"^\d{6}$")


class ResendVerificationOtpRequest(BaseModel):
    email: EmailStr
