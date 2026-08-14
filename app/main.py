import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db, engine
from app import models
from app.api.auth import router as auth_router
from app.api.profile import router as profile_router


models.user.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Scholar AI API",
    version="1.0.0"
)


origins = [
    "http://localhost:3000",  # إذا كان يستخدم React/Next.js
    "http://localhost:5173",  # إذا كان يستخدم Vite
    "http://127.0.0.1:5500",  # إذا كان يستخدم Live Server
]
# إضافة دومين الإنتاج للفرونت إند تلقائياً في حال وجوده بالبيئة
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],           # السماح بـ POST, GET, PUT, DELETE... الخ
    allow_headers=["*"],           # السماح بكافة الـ Headers مثل Authorization
)

app.include_router(auth_router)
app.include_router(profile_router)
@app.get("/")
def root():
    return {"message": "Scholar AI API is Running!"}
