import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserCreate, UserLogin, Token,
    ForgotPasswordRequest, ResetPasswordRequest, ChangePasswordRequest,
    MessageResponse, VerifyEmailRequest, ResendVerificationOtpRequest,
)
from app.core.security import (
    hash_password, verify_password, create_access_token,
    create_reset_token, verify_reset_token, get_current_user
)
from app.core.config import settings
from app.core.mailer import (
    EmailDeliveryError,
    send_reset_password_email,
    send_verification_otp_email,
)
from app.services.email_verification import (
    clear_verification_otp,
    issue_verification_otp,
    otp_matches,
    utc_now_naive,
)

router = APIRouter(prefix='/auth', tags=['Authentication'])
logger = logging.getLogger("uvicorn.error")


def _otp_retry_after(user: User, now) -> int | None:
    if not user.email_verification_otp_sent_at:
        return None
    cooldown = timedelta(
        seconds=settings.EMAIL_VERIFICATION_OTP_RESEND_COOLDOWN_SECONDS
    )
    elapsed = now - user.email_verification_otp_sent_at
    if elapsed >= cooldown:
        return None
    return max(1, int((cooldown - elapsed).total_seconds()))


def _raise_if_otp_cooldown_active(user: User, now) -> None:
    retry_after = _otp_retry_after(user, now)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait before requesting another verification OTP",
            headers={"Retry-After": str(retry_after)},
        )


def _clear_failed_otp(user: User, db: Session) -> None:
    clear_verification_otp(user)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.error(
            "Could not clear failed verification OTP for user_id=%s",
            user.id,
        )


def _issue_and_send_verification_otp(
    user: User,
    db: Session,
    *,
    database_error_detail: str,
    delivery_error_detail: str,
) -> None:
    otp = issue_verification_otp(user)
    try:
        db.commit()
        db.refresh(user)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=database_error_detail,
        ) from exc

    try:
        send_verification_otp_email(user.email, otp)
    except EmailDeliveryError as exc:
        logger.error(
            "Verification email failed user_id=%s provider=resend status=%s type=%s message=%s",
            user.id,
            exc.status_code or "unavailable",
            exc.error_type or "unavailable",
            str(exc),
        )
        _clear_failed_otp(user, db)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=delivery_error_detail,
        ) from exc
    except Exception as exc:
        # Unexpected adapters and test doubles may bypass the safe mail wrapper.
        # Log only the exception type so message bodies and OTPs cannot leak.
        logger.error(
            "Verification email failed user_id=%s error_type=%s",
            user.id,
            type(exc).__name__,
        )
        _clear_failed_otp(user, db)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=delivery_error_detail,
        ) from exc

@router.post(
    '/register', response_model=MessageResponse, status_code=status.HTTP_201_CREATED
)
def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    existing_user = (
        db.query(User)
        .filter(User.email == user_data.email)
        .with_for_update()
        .first()
    )
    if existing_user:
        if existing_user.is_email_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        _raise_if_otp_cooldown_active(existing_user, utc_now_naive())
        _issue_and_send_verification_otp(
            existing_user,
            db,
            database_error_detail="Could not update the pending registration",
            delivery_error_detail=(
                "The account is still pending, but the verification email could not "
                "be sent. Please try again."
            ),
        )
        return {
            "message": "Registration successful. Verification OTP sent to your email."
        }

    hashed_pwd = hash_password(user_data.password)

    # ✅ التعديل: إسناد full_name من user_data
    new_user = User(
        full_name=user_data.full_name,
        email=user_data.email,
        hashed_password=hashed_pwd,
        role=user_data.role if user_data.role else "student",
        is_email_verified=False,
    )
    try:
        db.add(new_user)
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="البريد الإلكتروني مسجل بالفعل",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="تعذر إنشاء الحساب بسبب خطأ في قاعدة البيانات",
        ) from exc
    _issue_and_send_verification_otp(
        new_user,
        db,
        database_error_detail="Could not create the account due to a database error",
        delivery_error_detail=(
            "Account created, but the verification email could not be sent. "
            "Please resend it."
        ),
    )

    return {
        "message": "Registration successful. Verification OTP sent to your email."
    }


@router.post('/login', response_model=Token)
def login_user(
    user_data: UserLogin,
    db: Session = Depends(get_db)
):
    user = (
        db.query(User)
        .filter(User.email == user_data.email)
        .first()
    )

    if not user or not verify_password(
        user_data.password,
        user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail='البريد الإلكتروني أو كلمة المرور غير صحيحة'
        )
    
    if not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required",
        )

    access_token = create_access_token(data={'sub': str(user.id), 'role': user.role})
    return {'access_token': access_token, 'token_type': 'bearer'}

@router.post('/verify-email', response_model=MessageResponse)
def verify_email(request: VerifyEmailRequest, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter(User.email == request.email)
        .with_for_update()
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP",
        )

    if user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP",
        )

    now = utc_now_naive()
    if (
        not user.email_verification_otp_hash
        or not user.email_verification_otp_expires_at
        or user.email_verification_otp_expires_at <= now
        or not otp_matches(request.otp, user.email_verification_otp_hash)
    ):
        if (
            user.email_verification_otp_expires_at
            and user.email_verification_otp_expires_at <= now
        ):
            clear_verification_otp(user)
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP",
        )

    user.is_email_verified = True
    clear_verification_otp(user)
    db.commit()
    return {"message": "Email verified successfully"}


@router.post('/resend-verification-otp', response_model=MessageResponse)
def resend_verification_otp(
    request: ResendVerificationOtpRequest,
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(User.email == request.email)
        .with_for_update()
        .first()
    )

    # Keep the response generic so this endpoint cannot enumerate accounts.
    if not user:
        return {
            "message": "If an unverified account exists, a verification OTP has been sent."
        }

    if user.is_email_verified:
        return {"message": "Email is already verified"}

    _raise_if_otp_cooldown_active(user, utc_now_naive())
    _issue_and_send_verification_otp(
        user,
        db,
        database_error_detail="Could not update the verification OTP",
        delivery_error_detail=(
            "The verification email could not be sent. Please try again."
        ),
    )

    return {"message": "Verification OTP sent to your email"}


@router.post(
    '/forgot-password',
    response_model=MessageResponse,
    summary='Request password reset email',
)
async def forgot_password(
    request: ForgotPasswordRequest, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == request.email).first()
    if user:
        reset_token = create_reset_token(email=user.email)
        # إرسال الإيميل في الخلفية لعدم إبطاء الـ API
        background_tasks.add_task(send_reset_password_email, user.email, reset_token)
    
    return {'message': 'إذا كان البريد مسجلاً، فقد تم إرسال رابط إعادة التعيين إلى إيميلك.'}

@router.post(
    '/reset-password',
    response_model=MessageResponse,
    summary='Reset password with email token',
    responses={
        400: {"description": "Invalid or expired token"},
        404: {"description": "User not found"},
    },
)
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    email = verify_reset_token(request.token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail='الرمز غير صالح أو انتهت صلاحيته!'
        )
    
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='المستخدم غير موجود')
    
    user.hashed_password = hash_password(request.new_password)
    db.commit()
    return {'message': 'تم تغيير كلمة المرور بنجاح! يمكنك الآن تسجيل الدخول.'}

@router.post(
    '/change-password',
    response_model=MessageResponse,
    summary='Change password (authenticated)',
    responses={
        400: {"description": "Old password is incorrect"},
        401: {"description": "Missing or invalid Bearer token"},
    },
)
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not verify_password(data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="كلمة المرور القديمة غير صحيحة"
        )
    
    current_user.hashed_password = hash_password(data.new_password)
    db.commit()
    return {'message': 'تم تغيير كلمة المرور بنجاح!'}
