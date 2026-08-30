"""
admin.py
--------
Endpoints used by the reviewer/admin role only:
  - GET /admin/merchants: list all merchants with optional status filter
  - GET /admin/merchants/{id}: full merchant detail + audit trail + verification breakdown
  - POST /admin/merchants/{id}/verify: admin-triggered verification (LLM + external checks)
  - POST /admin/merchants/{id}/decide: the mandatory human sign-off
  - POST /admin/batch-test: runs the synthetic accuracy report

All routes are protected by `require_role`, so a regular merchant token
cannot access another merchant's data.

Phase 3 changes:
  - The automatic verification pipeline (previously in documents.py) has
    been moved here as a manual, admin-triggered action. This gives the
    admin control over when checks run and shows them the full structured
    breakdown before they make a decision.
  - decide_application now accepts an optional note — if rejecting and no
    note is supplied, the stored rejection_cause (auto-generated from the
    mismatched checks) is used instead.
"""

import json as _json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from auth import require_role
import decision
import documents as documents_module
import verify
from db import AuditLog, Document, Merchant, get_db
from schemas import (
    AuditLogEntryResponse,
    BatchTestReport,
    MerchantDetailResponse,
    MerchantSummaryResponse,
    ResolveExceptionRequest,
    VerificationBreakdown,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _normalize_checks(checks: list[dict]) -> list[dict]:
    """Ensure the 'matched' field is always a bool, not a string."""
    for entry in checks:
        if isinstance(entry.get("matched"), str):
            entry["matched"] = entry["matched"].lower() == "true"
    return checks


def _merchant_to_summary(m: Merchant) -> MerchantSummaryResponse:
    """Maps a Merchant ORM model to its summary response shape."""
    return MerchantSummaryResponse(
        merchant_id=m.id,
        business_name=m.business_name,
        email=m.email,
        onboarding_status=m.onboarding_status,
        created_at=m.created_at.isoformat(),
    )


@router.get("/merchants", response_model=list[MerchantSummaryResponse])
def list_merchants(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    _reviewer: Merchant = Depends(require_role("reviewer", "admin")),
) -> list[MerchantSummaryResponse]:
    """
    Returns a list of all merchant accounts, optionally filtered by
    onboarding_status. Used by the admin panel's status-filter tabs.
    """
    query = db.query(Merchant).filter(Merchant.role == "merchant")
    if status_filter:
        query = query.filter(Merchant.onboarding_status == status_filter)
    return [_merchant_to_summary(m) for m in query.all()]


@router.get("/merchants/{merchant_id}", response_model=MerchantDetailResponse)
def get_merchant_detail(
    merchant_id: int,
    db: Session = Depends(get_db),
    _reviewer: Merchant = Depends(require_role("reviewer", "admin")),
) -> MerchantDetailResponse:
    """
    Returns full merchant detail including active documents, extracted
    fields, OCR confidence, the structured verification breakdown
    (matched/mismatched checks), and the complete audit trail.
    """
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")

    active_docs = db.query(Document).filter(
        Document.merchant_id == merchant_id, Document.is_active == True
    ).all()
    audit_entries = db.query(AuditLog).filter(
        AuditLog.merchant_id == merchant_id
    ).order_by(AuditLog.created_at.asc()).all()

    return MerchantDetailResponse(
        merchant_id=merchant.id,
        business_name=merchant.business_name,
        email=merchant.email,
        onboarding_status=merchant.onboarding_status,
        rejection_reason=merchant.rejection_reason,
        matched_checks=_normalize_checks(_json.loads(merchant.matched_checks)) if merchant.matched_checks else None,
        mismatched_checks=_normalize_checks(_json.loads(merchant.mismatched_checks)) if merchant.mismatched_checks else None,
        rejection_cause=merchant.rejection_cause,
        # Reuse the existing mapper from documents.py to avoid duplicating
        # the Document-to-response mapping logic.
        documents=[documents_module._to_response(d) for d in active_docs],
        audit_trail=[
            AuditLogEntryResponse(
                action=a.action,
                reason=a.reason,
                document_id=a.document_id,
                created_at=a.created_at.isoformat(),
            )
            for a in audit_entries
        ],
    )


@router.post("/merchants/{merchant_id}/verify", response_model=MerchantDetailResponse)
def verify_application(
    merchant_id: int,
    db: Session = Depends(get_db),
    _reviewer: Merchant = Depends(require_role("reviewer", "admin")),
) -> MerchantDetailResponse:
    """
    Phase 3: admin-triggered verification. Runs the LLM cross-document
    consistency check + all 5 simulated external verification sources
    on demand, storing the full structured breakdown on the Merchant row.

    Precondition: onboarding_status must be \"submitted\".
    Postcondition: onboarding_status becomes \"verified_matching\" (no
    mismatches) or \"verified_mismatched\" (one or more mismatches).

    This replaces the automatic pipeline that previously ran in
    documents.py's _run_verification_if_ready(). The admin now decides
    when to verify, and sees the complete picture before making a decision.
    """
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")
    if merchant.onboarding_status != "submitted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a submitted application can be verified",
        )

    # --- Step 1: Gather extracted fields from all active documents ---
    active_docs = db.query(Document).filter(
        Document.merchant_id == merchant_id, Document.is_active == True
    ).all()
    fields_by_type = {
        d.doc_type: _json.loads(d.extracted_fields_json)
        for d in active_docs
        if d.extracted_fields_json
    }

    # --- Step 2: LLM cross-document consistency check ---
    try:
        llm_result = verify.cross_verify_documents(fields_by_type)
    except Exception:
        logger.warning("LLM cross-verification failed, continuing with external checks only", exc_info=True)
        llm_result = None

    # Convert LLM findings into CheckResult entries
    llm_matched: list[dict[str, str]] = []
    llm_mismatched: list[dict[str, str]] = []
    if llm_result is not None:
        for finding in llm_result.findings:
            entry = {
                "check_name": f"llm_cross_check_{finding.field_name}",
                "document_type": _determine_doc_type_for_field(finding.field_name, fields_by_type),
                "matched": finding.consistent,
                "detail": finding.reasoning,
            }
            if finding.consistent:
                llm_matched.append(entry)
            else:
                llm_mismatched.append(entry)

    # --- Step 3: External verification sources (all 5, no short-circuit) ---
    pan_fields = fields_by_type.get("PAN", {})
    bank_fields = fields_by_type.get("BANK_PROOF", {})
    pan_number = pan_fields.get("pan_number", "")
    account_number = bank_fields.get("account_number", "")

    external_breakdown = decision.check_external_sources(db, pan_number, account_number or None)

    # --- Step 4: Merge LLM + external findings into one breakdown ---
    all_matched = llm_matched + [cm.model_dump() for cm in external_breakdown.matched]
    all_mismatched = llm_mismatched + [cm.model_dump() for cm in external_breakdown.mismatched]

    # Ensure matched field is always a bool (not a string from old data)
    for entry in all_matched:
        entry["matched"] = bool(entry["matched"])
    for entry in all_mismatched:
        entry["matched"] = bool(entry["matched"])

    # --- Step 5: Store on the Merchant row ---
    merchant.matched_checks = _json.dumps(all_matched)
    merchant.mismatched_checks = _json.dumps(all_mismatched)

    if all_mismatched:
        merchant.rejection_cause = verify.generate_rejection_cause(all_mismatched)
        merchant.onboarding_status = "verified_mismatched"
    else:
        merchant.rejection_cause = None
        merchant.onboarding_status = "verified_matching"

    # Log the verification run for the audit trail
    db.add(AuditLog(
        merchant_id=merchant.id,
        action="verification_run",
        reason=f"Admin-triggered verification: {len(all_matched)} matched, {len(all_mismatched)} mismatched",
    ))
    db.commit()
    db.refresh(merchant)

    # Return the full detail response
    return get_merchant_detail(merchant_id, db, _reviewer=_reviewer)


def _determine_doc_type_for_field(field_name: str, fields_by_type: dict) -> str:
    """Heuristic to map an LLM finding's field_name to the document type it came from."""
    for doc_type, fields in fields_by_type.items():
        if field_name in fields:
            return doc_type
    return "unknown"


@router.post("/merchants/{merchant_id}/decide", response_model=MerchantSummaryResponse)
def decide_application(
    merchant_id: int,
    payload: ResolveExceptionRequest,
    db: Session = Depends(get_db),
    reviewer: Merchant = Depends(require_role("reviewer", "admin")),
) -> MerchantSummaryResponse:
    """
    Phase 3 update: the mandatory human sign-off now requires the merchant
    to be in a \"verified_matching\" or \"verified_mismatched\" state (after
    the admin has run verification).

    Approving is one click (no note required).
    Rejecting defaults to the stored rejection_cause if no note is supplied;
    if the admin supplies a note, it takes precedence (admin override).
    """
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")
    if merchant.onboarding_status not in ("verified_matching", "verified_mismatched"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a verified application (matching or mismatched) can be decided on",
        )

    if payload.decision == "approved":
        merchant.onboarding_status = "active"
        merchant.rejection_reason = None
    else:
        merchant.onboarding_status = "rejected"
        # Use the admin-supplied note if provided; otherwise fall back
        # to the auto-generated rejection_cause stored during verification.
        if payload.note and payload.note.strip():
            merchant.rejection_reason = verify.humanize_reason(payload.note)
        elif merchant.rejection_cause:
            merchant.rejection_reason = merchant.rejection_cause
        else:
            merchant.rejection_reason = "Your application could not be verified. Please contact support for details."

    # Reflect the admin's final call on each active document too
    active_docs = db.query(Document).filter(
        Document.merchant_id == merchant_id, Document.is_active == True
    ).all()
    for doc in active_docs:
        doc.verification_status = "approved" if payload.decision == "approved" else "rejected"

    decision_note = payload.note or merchant.rejection_cause or "No note provided"
    db.add(AuditLog(
        merchant_id=merchant.id,
        action="manual_review_resolution",
        reason=f"Reviewer decision: {payload.decision} — {decision_note} (by {reviewer.email})",
    ))
    db.commit()

    return _merchant_to_summary(merchant)


@router.post("/batch-test", response_model=BatchTestReport)
def run_batch_test(
    db: Session = Depends(get_db),
    _admin: Merchant = Depends(require_role("admin")),
) -> BatchTestReport:
    """
    Reports accuracy across every merchant currently in the system.
    Intended to be run against the seeded synthetic dataset (see
    seed.py) so judges can see measured accuracy, not just a live demo.

    Note: "correctness" here is derived from each seeded merchant's
    `expected_outcome` audit note written by seed.py, so this reflects
    ground truth built into the test data — not a guess.
    """
    merchants = db.query(Merchant).filter(Merchant.role == "merchant").all()
    total = len(merchants)
    correctly_approved = 0
    correctly_flagged = 0
    false_approvals = 0
    exceptions: list[str] = []

    for merchant in merchants:
        expected_log = (
            db.query(AuditLog)
            .filter(AuditLog.merchant_id == merchant.id, AuditLog.action == "expected_outcome")
            .first()
        )
        expected = expected_log.reason if expected_log else None
        actual = merchant.onboarding_status

        if expected == "approved" and actual == "active":
            correctly_approved += 1
        elif expected == "flagged" and actual in ("flagged", "rejected"):
            correctly_flagged += 1
        elif expected == "flagged" and actual == "active":
            false_approvals += 1
            exceptions.append(f"Merchant {merchant.id}: expected flag but was auto-approved")
        elif expected is None:
            exceptions.append(f"Merchant {merchant.id}: no expected outcome recorded, could not score")

    accuracy = (
        ((correctly_approved + correctly_flagged) / total) * 100 if total else 0.0
    )

    return BatchTestReport(
        total_records=total,
        correctly_approved=correctly_approved,
        correctly_flagged=correctly_flagged,
        false_approvals=false_approvals,
        accuracy_percent=round(accuracy, 2),
        unresolved_exceptions=exceptions,
    )
