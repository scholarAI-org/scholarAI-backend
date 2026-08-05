from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# رابط الاتصال بقاعدة بيانات PostgreSQL
# الصيغة: postgresql://username:password@localhost:5432/dbname
# استبدل postgres و كلمة المرور واسم الداتابيز بالتفاصيل الخاصة بك
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:123456@localhost:5432/scholarai_db"

# إنشاء محرك الاتصال (Engine)
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# إنشاء الجلسة (Session) التي ستتعامل مع عمليات التعديل والاستعلام
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# الـ Base الذي سترث منه جميع الجداول (Models) لاحقاً
Base = declarative_base()

# دالة مخصصة لإعطاء جلسة اتصال لكل طلب (Dependency) وإغلاقها فور الانتهاء
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()