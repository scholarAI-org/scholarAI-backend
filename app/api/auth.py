from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserLogin, Token
from app.core.security import hash_password, verify_password, create_access_token
from app.schemas.user import (
    UserCreate, UserResponse, UserLogin, Token, 
    ForgotPasswordRequest, ResetPasswordRequest
)
from app.core.security import (
    hash_password, verify_password, create_access_token, 
    create_reset_token, verify_reset_token
)
router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    # 1. التحقق مما إذا كان البريد الإلكتروني مستخدماً من قبل
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="البريد الإلكتروني مسجل بالفعل!"
        )

    # 2. تشفير كلمة المرور
    hashed_pwd = hash_password(user_data.password)

    # 3. إنشاء مستخدم جديد
    new_user = User(
        email=user_data.email,
        hashed_password=hashed_pwd,
        role=user_data.role
    )

    # 4. حفظ البيانات في الداتابيز
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post("/login", response_model=Token)
def login_user(user_data: UserLogin, db: Session = Depends(get_db)):
    # 1. البحث عن المستخدم بالبريد
    user = db.query(User).filter(User.email == user_data.email).first()
    
    # 2. التحقق من وجود المستخدم وصحة كلمة المرور
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="البريد الإلكتروني أو كلمة المرور غير صحيحة"
        )
    
    # 3. إنشاء الـ Access Token
    access_token = create_access_token(data={"sub": str(user.id), "role": user.role})

    return {"access_token": access_token, "token_type": "bearer"}


# 1. مسار طلب إعادة تعيين كلمة المرور
@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    
    # لمزيد من الأمان: حتى لو الإيميل مش موجود بنرجع نفس الرسالة عشان نحمي الخصوصية
    if not user:
        return {"message": "إذا كان البريد مسجلاً، فقد تم إرسال رابط إعادة التعيين."}
    
    # إنشاء الـ Reset Token
    reset_token = create_reset_token(email=user.email)
    
    # 💡 ملاحظة: هنا في البيئة الإنتاجية يتم استخدام مكتبة مثل fastapi-mail لإرسال الإيميل
    # حالياً نرجع التوكن في الـ Response للتعلم والتجربة بسهولة
    return {
        "message": "إذا كان البريد مسجلاً، فقد تم إرسال رابط إعادة التعيين.",
        "reset_token": reset_token  # سينتقل للإيميل في التطبيق الحقيقي
    }


# 2. مسار تنفيذ إعادة تعيين كلمة المرور
@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    # التحقق من صحة التوكن وانتهائه
    email = verify_reset_token(request.token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="الرمز غير صالح أو انتهت صلاحيته!"
        )
    
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="المستخدم غير موجود"
        )
    
    # تحديث كلمة المرور وتشفيرها
    user.hashed_password = hash_password(request.new_password)
    db.commit()
    
    return {"message": "تم تغيير كلمة المرور بنجاح! يمكنك الآن تسجيل الدخول."}