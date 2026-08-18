from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from app.models.profile import Profile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserCreate, UserResponse, UserLogin, Token,
    ForgotPasswordRequest, ResetPasswordRequest, ChangePasswordRequest
)
from app.core.security import (
    hash_password, verify_password, create_access_token,
    create_reset_token, verify_reset_token, get_current_user
)
from app.core.mailer import send_reset_password_email

router = APIRouter(prefix='/auth', tags=['Authentication'])

# 1. التسجيل
@router.post('/register', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="البريد الإلكتروني مسجل بالفعل"
        )

    hashed_pwd = hash_password(user_data.password)

    new_user = User(
        email=user_data.email,
        hashed_password=hashed_pwd,
        role=user_data.role if user_data.role else "student"
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return new_user

    except Exception:
        db.rollback()
        raise


# 2. تسجيل الدخول
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
    
    access_token = create_access_token(data={'sub': str(user.id), 'role': user.role})
    return {'access_token': access_token, 'token_type': 'bearer'}

# 3. نسيان كلمة المرور (إرسال الإيميل)
@router.post('/forgot-password')
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

# 4. إعادة تعيين كلمة المرور (استقبال التوكن + الكلمة الجديدة من الفرونت إند)
@router.post('/reset-password')
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

# 5. تغيير كلمة المرور (من داخل الحساب بعد تسجيل الدخول)
@router.post('/change-password')
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
