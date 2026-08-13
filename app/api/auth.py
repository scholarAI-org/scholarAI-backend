from fastapi import APIRouter, Depends, HTTPException, status
from app.models.profile import Profile
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserLogin, Token
from app.core.security import hash_password, verify_password, create_access_token
from app.schemas.user import UserCreate, UserResponse, UserLogin, Token, ForgotPasswordRequest, ResetPasswordRequest
from app.core.security import hash_password, verify_password, create_access_token, create_reset_token, verify_reset_token
router = APIRouter(prefix='/auth', tags=['Authentication'])
@router.post('/register', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_data: UserCreate, db: Session=Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='البريد الإلكتروني مسجل بالفعل!')
    else:
        hashed_pwd = hash_password(user_data.password)
        new_user = User(email=user_data.email, hashed_password=hashed_pwd, role='student')

        try:
            db.add(new_user)
            db.flush()

            new_profile = Profile(user_id=new_user.id, full_name=user_data.full_name)
            db.add(new_profile)

            db.commit()
            db.refresh(new_user)
            return new_user

        except Exception:
            db.rollback()
            raise
@router.post('/login', response_model=Token)
def login_user(user_data: UserLogin, db: Session=Depends(get_db)):
    user = db.query(User).filter(User.email == user_data.email).first()
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='البريد الإلكتروني أو كلمة المرور غير صحيحة')
    else:
        access_token = create_access_token(data={'sub': str(user.id), 'role': user.role})
        return {'access_token': access_token, 'token_type': 'bearer'}
@router.post('/forgot-password')
def forgot_password(request: ForgotPasswordRequest, db: Session=Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        return {'message': 'إذا كان البريد مسجلاً، فقد تم إرسال رابط إعادة التعيين.'}
    else:
        reset_token = create_reset_token(email=user.email)
        return {'message': 'إذا كان البريد مسجلاً، فقد تم إرسال رابط إعادة التعيين.', 'reset_token': reset_token}
@router.post('/reset-password')
def reset_password(request: ResetPasswordRequest, db: Session=Depends(get_db)):
    email = verify_reset_token(request.token)
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='الرمز غير صالح أو انتهت صلاحيته!')
    else:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='المستخدم غير موجود')
        else:
            user.hashed_password = hash_password(request.new_password)
            db.commit()
            return {'message': 'تم تغيير كلمة المرور بنجاح! يمكنك الآن تسجيل الدخول.'}
