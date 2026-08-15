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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(profile_router)

@app.get("/")
def root():
    return {"message": "Scholar AI API is Running!"}

