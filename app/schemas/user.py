from pydantic import BaseModel, EmailStr ,field_validator
from typing import Optional
import re
# مخطط البيانات التي سيرسلها المستخدم عند التسجيل
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: Optional[str] = "student"

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
    email: EmailStr
    role: str
    is_active: bool

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

# مخطط إعادة تعيين كلمة المرور باستخدام الرمز
class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('كلمة المرور يجب أن تكون 8 أحرف على الأقل')
        if not re.search(r"\d", v):
            raise ValueError('كلمة المرور يجب أن تحتوي على رقم واحد على الأقل')
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError('كلمة المرور يجب أن تحتوي على رمز خاص واحد على الأقل (!@#$%^&*)')
        return v