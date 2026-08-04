from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db, engine
from app import models  # استدعاء الـ models لتفعيل الكود
from app.api.auth import router as auth_router

# إنشاء الجداول في الداتابيز
models.user.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Scholar AI API",
    version="1.0.0"
)
app.include_router(auth_router)

@app.get("/")
def root():
    return {"message": "Scholar AI API is Running!"}

