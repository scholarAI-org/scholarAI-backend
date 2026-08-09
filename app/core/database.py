import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 1. قراءة رابط قاعدة البيانات من متغيرات البيئة (الخاصة بـ Render)
DATABASE_URL = os.getenv("DATABASE_URL")

# 2. إذا كان الرابط يبدأ بـ postgres:// (تنسيق قديم)، نعدله إلى postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 3. إذا لم يجد رابط سحابي (يعني أنكِ تعملين محلياً على جهازك)، استخدم الرابط المحلي
if not DATABASE_URL:
    DATABASE_URL = "postgresql://postgres:123456@localhost:5432/scholarai_db"

# إنشاء محرك الاتصال (Engine)
engine = create_engine(DATABASE_URL)

# إنشاء الجلسة (Session)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# الـ Base الخاص بالنودلز/النماذج
Base = declarative_base()

# دالة مخصصة لإعطاء جلسة اتصال لكل طلب (Dependency)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()