"""
config.py
---------
Single source of truth for every configurable value in the backend.
Nothing in this project should hardcode a secret, threshold, or magic
string directly inside business logic — it belongs here instead.

Values are loaded from environment variables (with safe local-dev
defaults) so the same code works in Docker, CI, or a developer's machine
without any code changes.
"""

import os
from pathlib import Path

# Load .env file if present — only needed for local dev; Docker uses env_file.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on shell env vars


class Settings:
    # --- App ---
    APP_NAME: str = "Merchant Onboarding Copilot"
    ENV: str = os.getenv("ENV", "development")

    # --- Database ---
    # SQLite is used for local/demo simplicity. In Docker, the DB file
    # lives at /app/db_data/app.db which is backed by a named volume,
    # so data survives container restarts. Locally it writes next to
    # this file as app.db.
    _DB_DIR = Path(os.getenv("DB_DATA_DIR", str(Path(__file__).parent)))
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{_DB_DIR / 'app.db'}"
    )

    # --- Auth / JWT ---
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = int(os.getenv("JWT_EXPIRY_MINUTES", "60"))

    # --- LLM API (OpenAI-compatible: Groq, OpenAI, etc.) ---
    # Single Groq key powers BOTH document extraction (vision OCR, see
    # ocr.py) and LLM cross-verification (verify.py). LLM_MODEL must be
    # a Groq vision-capable model for extraction to work — the default
    # qwen/qwen3.8-27b is one (gpt-oss models are text-only on Groq).
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")
    # Optional comma-separated Groq keys from OTHER accounts. Groq rate
    # limits are per-account, so on a 401/403/429 the OCR layer rotates
    # to the next key for headroom. Keys on the SAME account add nothing.
    LLM_FALLBACK_KEYS: list[str] = [
        k.strip() for k in os.getenv("LLM_FALLBACK_KEYS", "").split(",") if k.strip()
    ]

    # --- CORS ---
    ALLOWED_ORIGINS: list[str] = os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:5173"
    ).split(",")

    # --- File upload constraints ---
    MAX_UPLOAD_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB
    ALLOWED_CONTENT_TYPES: tuple[str, ...] = (
        "image/jpeg",
        "image/png",
        "application/pdf",
    )
    UPLOAD_DIR: Path = Path(__file__).parent / "uploaded_documents"

    # --- Test dataset ---
    # Directory containing the synthetic test documents (PAN, GST, Bank
    # proof images + summary.csv) that judges can download from the
    # landing page to independently verify the system.
    # On Render/Docker, set TEST_DATASET_DIR env var to /app/test_documents
    TEST_DATASET_DIR: Path = Path(os.getenv(
        "TEST_DATASET_DIR",
        str(Path(__file__).parent.parent / "test_documents" / "test_documents")
    ))

    # --- Verification thresholds ---
    # Anything below this OCR confidence is never auto-approved.
    MIN_OCR_CONFIDENCE: float = 0.80
    # Fuzzy-match threshold (0-100) for comparing names across documents.
    NAME_MATCH_THRESHOLD: int = 85

    # --- Validation patterns ---
    PAN_REGEX: str = r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$"
    GST_REGEX: str = r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}\d[Z]{1}[A-Z\d]{1}$"
    IFSC_REGEX: str = r"^[A-Z]{4}0[A-Z0-9]{6}$"

    # --- Document types supported in MVP ---
    SUPPORTED_DOCUMENT_TYPES: tuple[str, ...] = ("PAN", "GST", "BANK_PROOF")

    # --- Risk scoring (Feature 1) ---
    # Points added to a merchant's risk score for each type of mismatched
    # check. Capped at MAX_RISK_SCORE. Weights reflect how serious each
    # failure type is.
    RISK_WEIGHTS: dict[str, int] = {
        "govt_database": 30,
        "ckyc_records": 20,
        "automated_verification": 20,
        "bank_account_validation": 20,
        "compliance_reviews": 10,
        "llm_cross_check": 15,
        "fraud_ring_pan": 40,
        "fraud_ring_bank": 40,
        # A suspected prompt-injection payload in merchant-supplied
        # document text is a strong fraud signal — the merchant routes to
        # human review, never verifies clean (see injection_guard.py).
        "prompt_injection_suspected": 40,
    }
    MAX_RISK_SCORE: int = 100

    def validate(self) -> None:
        """Fail fast at startup if required secrets are missing."""
        missing = []
        if not self.JWT_SECRET_KEY:
            missing.append("JWT_SECRET_KEY")
        if not self.LLM_API_KEY:
            missing.append("LLM_API_KEY")
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Copy .env.example to .env and fill these in."
            )


settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
