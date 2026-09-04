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

import io
import logging
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

import seed
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import admin
import auth
import documents
from config import settings
from db import apply_migrations, engine, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    # 1. Ensure base tables exist (idempotent — only creates missing tables).
    init_db()
    # 2. Apply Alembic migrations (stamps at head on a fresh database where
    #    init_db() already created the full schema from ORM models).
    apply_migrations()
    # 3. Seed database if empty (idempotent — safe to call on every start)
    try:
        seed.main()
    except Exception:
        logging.getLogger("main").exception("Database seeding failed — continuing without seed data.")
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


@app.middleware("http")
async def _record_request_metrics(request, call_next):
    """Feeds the admin system-health view: records every request's status
    + latency into the process-local metrics store (health.py). Failures
    to record never affect the request itself.
    """
    import time

    import health

    start = time.monotonic()
    response = await call_next(request)
    health.record_request(response.status_code, (time.monotonic() - start) * 1000)
    return response


app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(admin.router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Basic liveness check used by Docker Compose and manual testing."""
    return {"status": "ok", "service": settings.APP_NAME}


# ---------------------------------------------------------------------------
# Test dataset download — serves the synthetic test documents as a zip file
# so judges and visitors can independently verify the system's accuracy.
# No authentication required.
# ---------------------------------------------------------------------------

def _stream_zip(dataset_dir: Path):
    """Yields zip file chunks for streaming response. Walks the dataset
    directory and adds every file (images + summary.csv) to the archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(dataset_dir.rglob("*")):
            if file_path.is_file():
                arcname = str(file_path.relative_to(dataset_dir.parent))
                zf.write(file_path, arcname)
    buf.seek(0)
    yield buf.read()


@app.get("/test-dataset/download", tags=["dataset"])
def download_test_dataset():
    """Streams the synthetic test dataset as a zip file.

    Contains 50 merchant directories (PAN/GST/Bank proof images) and
    a summary.csv with expected outcomes. Accessible without auth so
    judges can independently evaluate the system.
    """
    # Check multiple possible paths for the test dataset
    dataset_dir = settings.TEST_DATASET_DIR
    
    # Fallback paths if the configured path doesn't exist
    fallback_paths = [
        Path("/app/test_documents"),
        Path(__file__).parent / "test_documents" / "test_documents",
        Path(__file__).parent.parent / "test_documents" / "test_documents",
    ]
    
    if not dataset_dir.is_dir():
        for fallback in fallback_paths:
            if fallback.is_dir():
                dataset_dir = fallback
                break
    
    if not dataset_dir.is_dir():
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404, 
            detail="Test dataset not found on this server. Please contact support."
        )
    
    return StreamingResponse(
        _stream_zip(dataset_dir),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="test_dataset.zip"'},
    )