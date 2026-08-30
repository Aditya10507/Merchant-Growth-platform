""" 
main.py
-------
FastAPI application entrypoint. Keeps only app wiring here (CORS, router
registration, startup tasks) — all business logic lives in its own
module (auth.py, documents.py, decision.py, etc.) so this file stays
short and readable.

Run locally with:
    uvicorn main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import admin
import auth
import documents
from config import settings
from db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    # 1. Ensure base tables exist (idempotent — only creates missing tables).
    init_db()
    # 2. Run Alembic migrations to apply any schema changes since last deploy.
    try:
        alembic_cfg = AlembicConfig("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
        alembic_command.upgrade(alembic_cfg, "head")
        logging.getLogger("main").info("Alembic migrations applied successfully.")
    except Exception:
        logging.getLogger("main").exception("Alembic migration failed — continuing with existing schema.")
    # Ensure the upload directory exists before any requests
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(admin.router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Basic liveness check used by Docker Compose and manual testing."""
    return {"status": "ok", "service": settings.APP_NAME}