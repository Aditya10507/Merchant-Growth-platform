"""
schemas.py
----------
Pydantic models define the request/response contracts for every endpoint.
Keeping these separate from the SQLAlchemy ORM models (db.py) follows the
Single Responsibility Principle: db.py describes storage, schemas.py
describes the API surface. Pydantic enforces types and validation rules
at the boundary, so invalid data never reaches business logic.
"""

import re
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from config import settings

DocumentType = Literal["PAN", "GST", "BANK_PROOF"]
VerificationStatus = Literal["uploaded", "verifying", "invalid_format", "temporarily_unavailable", "submitted", "approved", "flagged", "rejected"]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class SignupRequest(BaseModel):
    business_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, value: str) -> str:
        # Minimal strength rule: at least one letter and one digit.
        if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password must contain at least one letter and one digit")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    merchant_id: int
    business_name: str
    role: str


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class DocumentStatusResponse(BaseModel):
    id: int
    doc_type: DocumentType
    verification_status: VerificationStatus
    ocr_confidence: Optional[float] = None
    extracted_fields: Optional[dict[str, str]] = None
    rejection_reason: Optional[str] = None


class MerchantStatusResponse(BaseModel):
    merchant_id: int
    onboarding_status: str
    rejection_reason: Optional[str] = None
    documents: list[DocumentStatusResponse]


# ---------------------------------------------------------------------------
# LLM verification finding (structured, strict — see verify.py)
# ---------------------------------------------------------------------------


class FieldFinding(BaseModel):
    field_name: str
    consistent: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class LlmVerificationResult(BaseModel):
    overall_consistent: bool
    findings: list[FieldFinding]
    summary: str


# ---------------------------------------------------------------------------
# Admin / batch testing
# ---------------------------------------------------------------------------


class BatchTestReport(BaseModel):
    total_records: int
    correctly_approved: int
    correctly_flagged: int
    false_approvals: int
    accuracy_percent: float
    unresolved_exceptions: list[str]


# ---------------------------------------------------------------------------
# Structured verification breakdown (Phase 3: admin-triggered verify)
# Must be defined before MerchantDetailResponse which references it.
# ---------------------------------------------------------------------------


class CheckResult(BaseModel):
    """One check outcome — either matched or mismatched."""
    check_name: str
    document_type: str
    matched: bool
    detail: str


class VerificationBreakdown(BaseModel):
    """Full structured result of the admin-triggered verification run.

    Every source is checked unconditionally (no short-circuiting), so
    the admin sees the complete picture: what matched, what didn't, and
    what document each check relates to.
    """
    matched: list[CheckResult]
    mismatched: list[CheckResult]
    rejection_cause: Optional[str] = None


# ---------------------------------------------------------------------------
# Admin / reviewer panel schemas
# ---------------------------------------------------------------------------


class MerchantSummaryResponse(BaseModel):
    merchant_id: int
    business_name: str
    email: str
    onboarding_status: str
    risk_score: Optional[int] = None
    created_at: str


class AuditLogEntryResponse(BaseModel):
    action: str
    reason: str
    document_id: Optional[int] = None
    created_at: str


class MerchantDetailResponse(BaseModel):
    merchant_id: int
    business_name: str
    email: str
    onboarding_status: str
    rejection_reason: Optional[str] = None
    # Phase 3: structured verification breakdown stored on the Merchant row
    matched_checks: Optional[list[CheckResult]] = None
    mismatched_checks: Optional[list[CheckResult]] = None
    rejection_cause: Optional[str] = None
    risk_score: Optional[int] = None
    documents: list[DocumentStatusResponse]
    audit_trail: list[AuditLogEntryResponse]


class ResolveExceptionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    # Note is optional — if rejecting and no note is supplied, the stored
    # rejection_cause (auto-generated from mismatched checks) is used.
    note: Optional[str] = Field(default=None, max_length=1000)


class MaintenanceResult(BaseModel):
    """Result of an admin maintenance action (e.g. archiving test merchants)."""
    archived_count: int
    archived_emails: list[str]
    # Merchants that still participate in the batch-test accuracy report.
    remaining_count: int


# ---------------------------------------------------------------------------
# Live admin dashboard stats (Session 26: real-time summary cards)
# ---------------------------------------------------------------------------


class AdminStatsResponse(BaseModel):
    """Live summary of the review pipeline, computed fresh on every request.

    Counts exclude archived test merchants (is_test=True) — the dashboard
    must reflect real applicants only.

    Rates are computed over `processed` — merchants the admin has actually
    verified (verified_matching + verified_mismatched) — so "% flagged" and
    "fraud-ring rate" measure the AI's real hit rate, not dilution by
    un-reviewed pending rows.
    """
    applicants: int       # in-review: pending + submitted + verified_*
    approvals: int        # active (approved by admin)
    rejections: int       # rejected (by admin or pipeline)
    flagged: int          # verified_mismatched (routed to human review)
    fraud_ring_flagged: int  # merchants with a mismatched fraud_ring_* check
    processed: int        # verified_matching + verified_mismatched
    flagged_rate: float   # flagged / processed * 100 (0 if none processed)
    fraud_ring_rate: float  # fraud_ring_flagged / processed * 100


# ---------------------------------------------------------------------------
# Failure-injection demo mode (Feature 1: chaos panel)
# ---------------------------------------------------------------------------


class FaultStateResponse(BaseModel):
    """Snapshot of the demo fault-injection toggles (admin chaos panel)."""
    ocr_down: bool
    llm_down: bool
    sources_down: bool
    # Which faults are currently active, for logging/UI convenience.
    active: list[str]


class FaultToggleRequest(BaseModel):
    """Enable or disable one demo fault."""
    enabled: bool = True


# ---------------------------------------------------------------------------
# Empirical risk calibration (Feature 2: risk_eval.py)
# ---------------------------------------------------------------------------


class ClassScoreStatsResponse(BaseModel):
    count: int
    mean_score: float
    min_score: int
    max_score: int


class ThresholdRowResponse(BaseModel):
    threshold: int
    precision: float
    recall: float
    f1: float
    accuracy: float
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int


class RiskEvalReportResponse(BaseModel):
    total_labeled: int
    good_count: int
    bad_count: int
    replayed_count: int
    pipeline_scored_count: int
    good_stats: ClassScoreStatsResponse
    bad_stats: ClassScoreStatsResponse
    best_threshold: int
    best_f1: float
    best_confusion: dict[str, int]
    threshold_sweep: list[ThresholdRowResponse]
    weights_used: dict[str, int]


# ---------------------------------------------------------------------------
# Live system-health view (Feature 4: health.py)
# ---------------------------------------------------------------------------


class HealthBucketResponse(BaseModel):
    """Rolling stats for one service stream (OCR extraction or LLM
    cross-verification) over the sliding window."""
    count: int
    succeeded: int
    failed: int
    success_rate: Optional[float] = None
    avg_latency_ms: Optional[float] = None
    p95_latency_ms: Optional[float] = None


class RequestHealthResponse(BaseModel):
    """Rolling HTTP request stats over the sliding window."""
    total: int
    errors_5xx: int
    error_rate: Optional[float] = None
    avg_latency_ms: Optional[float] = None


class SystemHealthResponse(BaseModel):
    """The full admin system-health snapshot: service success rates,
    latencies, error counts over the recent window, plus a cross-link to
    the chaos panel's active faults."""
    uptime_seconds: float
    window_seconds: int
    ocr: HealthBucketResponse
    llm: HealthBucketResponse
    requests: RequestHealthResponse
    active_faults: list[str]
