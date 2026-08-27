from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, Field
from typing import Optional
import re

PASSWORD_DESCRIPTION = (
    "At least 8 characters, one digit, and one special character "
    "(!@#$%^&*(),.?\":{}|<>)"
)


class UserCreate(BaseModel):
    full_name: str = Field(
        ...,
        min_length=1,
        description="Required. JSON key must be full_name (not fullName).",
        examples=["Ahmed Ali"],
    )
    email: EmailStr = Field(..., examples=["user@example.com"])
    password: str = Field(..., description=PASSWORD_DESCRIPTION, examples=["Pass123!"])
    role: Optional[str] = Field(
        default="student",
        description="Optional. Defaults to student.",
        examples=["student"],
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("كلمة المرور يجب أن تكون 8 أحرف على الأقل")

        if not re.search(r"\d", v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رقم واحد على الأقل")

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError(
                "كلمة المرور يجب أن تحتوي على رمز خاص واحد على الأقل (!@#$%^&*)"
            )

        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "full_name": "Ahmed Ali",
                "email": "user@example.com",
                "password": "Pass123!",
                "role": "student",
            }
        }
    )


class UserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    role: str
    is_active: bool
    is_email_verified: bool

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    email: EmailStr = Field(..., examples=["user@example.com"])
    password: str = Field(..., examples=["Pass123!"])

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "Pass123!",
            }
        }
    )


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., examples=["user@example.com"])


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., description="Reset token from the email link.")
    new_password: str = Field(..., description=PASSWORD_DESCRIPTION, examples=["Pass123!"])

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("كلمة المرور يجب أن تكون 8 أحرف على الأقل")

        if not re.search(r"\d", v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رقم واحد على الأقل")

        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError(
                "كلمة المرور يجب أن تحتوي على رمز خاص واحد على الأقل (!@#$%^&*)"
            )

        return v


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(
        ...,
        min_length=8,
        description=PASSWORD_DESCRIPTION,
        examples=["Pass123!"],
    )

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("كلمة المرور يجب أن تكون 8 أحرف على الأقل")

        if not re.search(r"\d", v):
            raise ValueError("كلمة المرور يجب أن تحتوي على رقم واحد على الأقل")

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError(
                "كلمة المرور يجب أن تحتوي على رمز خاص واحد على الأقل (!@#$%^&*)"
            )

        return v


class MessageResponse(BaseModel):
    message: str


class VerifyEmailRequest(BaseModel):
    email: EmailStr = Field(..., examples=["user@example.com"])
    otp: str = Field(
        ...,
        pattern=r"^\d{6}$",
        description="Six-digit email verification code.",
        examples=["538204"],
    )


class ResendVerificationOtpRequest(BaseModel):
    email: EmailStr = Field(..., examples=["user@example.com"])
