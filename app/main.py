import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.api.auth import router as auth_router
from app.api.profile import router as profile_router
from app.api.scholarships import router as scholarships_router

logger = logging.getLogger("uvicorn.error")


app = FastAPI(
    title="Scholar AI API",
    version="1.0.0",
    description=(
        "Scholar AI backend API.\n\n"
        "Auth bodies use JSON with snake_case field names "
        "(`full_name`, `email`, `password`). "
        "Protected routes require a Bearer token from `/auth/login`."
    ),
    openapi_tags=[
        {
            "name": "Authentication",
            "description": "Register, login, and password reset. Send JSON, not form data.",
        },
        {
            "name": "Profile",
            "description": "Student profile, work experience, and languages. Requires Bearer auth.",
        },
        {
            "name": "Scholarships",
            "description": "Ingested scholarship listings (duplicate check and create).",
        },
        {
            "name": "System",
            "description": "Health and service status.",
        },
    ],
)


origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5500",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    origins.append(frontend_url.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    logger.exception("Integrity error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=400,
        content={"detail": "البيانات مكررة أو تخالف قيود قاعدة البيانات."},
    )


@app.exception_handler(OperationalError)
async def operational_error_handler(request: Request, exc: OperationalError):
    logger.exception("Database connection error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "تعذر الاتصال بقاعدة البيانات. "
                "تحقق من متغير DATABASE_URL ومن أن خدمة PostgreSQL تعمل."
            )
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "فشل تنفيذ العملية على قاعدة البيانات. "
                "راجع سجلات السيرفر أو تأكد أن الجداول مُحدَّثة (migrations)."
            )
        },
    )


app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(scholarships_router)


@app.get("/", tags=["System"], summary="API root")
def root():
    return {"message": "Scholar AI API is Running!"}


@app.get("/health", tags=["System"], summary="Health check")
def health():
    return {"status": "ok"}
