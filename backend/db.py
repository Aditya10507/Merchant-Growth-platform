"""
db.py
-----
Database engine, session management, and ORM models.

Tables:
  - merchants: registered merchant accounts (auth + onboarding status)
  - documents: uploaded documents per merchant, with OCR + verification results
  - audit_logs: append-only record of every verification decision and why
  - govt_database, ckyc_records, automated_verification,
    bank_account_validation, compliance_reviews:
        the 5 simulated "external" verification sources. These are real
        database tables (not in-memory mocks) seeded with synthetic data,
        as explicitly scoped in the PRD/Architecture docs.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from config import settings


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Core application tables
# ---------------------------------------------------------------------------


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="merchant")  # merchant | reviewer | admin
    onboarding_status = Column(String(30), nullable=False, default="pending")
    # Merchant-facing, plain-language explanation shown on the dashboard
    # when onboarding_status is "rejected" or "flagged". Always derived
    # from decision.py's technical reason via verify.humanize_reason() —
    # never an LLM-invented reason, only a rephrasing of one.
    rejection_reason = Column(Text, nullable=True)
    # Phase 3: structured verification results stored on the Merchant row.
    # matched_checks / mismatched_checks are JSON strings (list of CheckResult dicts).
    # rejection_cause is the auto-generated, admin-facing draft derived from mismatched_checks.
    matched_checks = Column(Text, nullable=True)    # JSON: list[CheckResult]
    mismatched_checks = Column(Text, nullable=True)  # JSON: list[CheckResult]
    rejection_cause = Column(Text, nullable=True)     # auto-generated from mismatched checks
    created_at = Column(DateTime, default=_utcnow)

    documents = relationship("Document", back_populates="merchant")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    doc_type = Column(String(20), nullable=False)  # PAN | GST | BANK_PROOF
    file_path = Column(String(500), nullable=False)
    extracted_fields_json = Column(Text, nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    verification_status = Column(String(30), nullable=False, default="uploaded")
    # uploaded -> verifying -> approved | flagged | rejected | invalid_format
    rejection_reason = Column(Text, nullable=True)
    # False once a merchant restarts their application after a rejection.
    # Kept (not deleted) so the audit trail/admin panel retains full
    # history; only active documents count toward the merchant's current
    # application and appear on their dashboard.
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    merchant = relationship("Merchant", back_populates="documents")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    action = Column(String(50), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, default=_utcnow)


# ---------------------------------------------------------------------------
# Simulated external verification sources (5 tables, per Architecture doc)
# ---------------------------------------------------------------------------


class GovtDatabase(Base):
    __tablename__ = "govt_database"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pan_number = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    dob = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)  # verified | invalid


class CkycRecord(Base):
    __tablename__ = "ckyc_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ckyc_id = Column(String(50), unique=True, nullable=False)
    pan_number = Column(String(20), nullable=False, index=True)
    kyc_status = Column(String(20), nullable=False)  # verified | pending | rejected
    last_updated = Column(String(30), nullable=False)


class AutomatedVerification(Base):
    __tablename__ = "automated_verification"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pan_number = Column(String(20), nullable=False, index=True)
    check_type = Column(String(50), nullable=False)
    result = Column(String(20), nullable=False)  # pass | fail
    confidence = Column(Float, nullable=False)


class BankAccountValidation(Base):
    __tablename__ = "bank_account_validation"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_number = Column(String(30), unique=True, nullable=False, index=True)
    ifsc = Column(String(15), nullable=False)
    name_match_score = Column(Float, nullable=False)  # 0-100
    verified = Column(String(10), nullable=False)  # yes | no


class ComplianceReview(Base):
    __tablename__ = "compliance_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pan_number = Column(String(20), nullable=False, index=True)
    flag_reason = Column(String(255), nullable=True)
    reviewer = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False)  # clear | flagged


# ---------------------------------------------------------------------------
# Engine + session factory
# ---------------------------------------------------------------------------

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables if they don't already exist."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency that yields a scoped DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
