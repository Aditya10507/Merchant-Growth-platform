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
from sqlalchemy import exists as sa_exists
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
    ClassScoreStatsResponse,
    FaultStateResponse,
    FaultToggleRequest,
    MaintenanceResult,
    MerchantDetailResponse,
    MerchantSummaryResponse,
    ResolveExceptionRequest,
    RiskEvalReportResponse,
    ThresholdRowResponse,
    VerificationBreakdown,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _normalize_checks(checks: list[dict]) -> list[dict]:
    """Ensure the 'matched' field is always a bool, not a string."""
    for entry in checks:
        if isinstance(entry.get("matched"), str):
            entry["matched"] = entry["matched"].lower() == "true"
    return checks


def _compute_risk_score(mismatched_checks: list[dict]) -> int:
    """Weighted sum of mismatched checks, capped at MAX_RISK_SCORE.

    Delegates to decision.compute_risk_score (the single source of truth
    for risk scoring — risk_eval.py uses the same function for its
    empirical calibration report).
    """
    return decision.compute_risk_score(mismatched_checks)


def _merchant_to_summary(m: Merchant) -> MerchantSummaryResponse:
    """Maps a Merchant ORM model to its summary response shape."""
    return MerchantSummaryResponse(
        merchant_id=m.id,
        business_name=m.business_name,
        email=m.email,
        onboarding_status=m.onboarding_status,
        risk_score=m.risk_score,
        created_at=m.created_at.isoformat(),
    )


@router.get("/merchants", response_model=list[MerchantSummaryResponse])
def list_merchants(
    status_filter: Optional[str] = None,
    sort_by_risk: bool = False,
    db: Session = Depends(get_db),
    _reviewer: Merchant = Depends(require_role("reviewer", "admin")),
) -> list[MerchantSummaryResponse]:
    """
    Returns a list of all merchant accounts, optionally filtered by
    onboarding_status. Used by the admin panel's status-filter tabs.

    Archived test merchants (is_test=True) are excluded — they were
    created by E2E test runs and only pollute the review queue.
    """
    query = db.query(Merchant).filter(
        Merchant.role == "merchant", Merchant.is_test == False
    )
    if status_filter:
        query = query.filter(Merchant.onboarding_status == status_filter)
    merchants = query.all()
    if sort_by_risk:
        # None (not yet verified) sorts last — an unscored merchant isn't
        # necessarily low-risk, it just hasn't been checked yet.
        merchants.sort(key=lambda m: (m.risk_score is None, -(m.risk_score or 0)))
    return [_merchant_to_summary(m) for m in merchants]


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
        risk_score=merchant.risk_score,
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

    Failure-recovery semantics (Feature 1): the LLM and the external
    verification sources are REQUIRED signals. If either is unavailable
    (real outage, or the admin chaos panel's llm_down/sources_down demo
    faults), verification is DEFERRED with a 503 — the merchant stays in
    \"submitted\" and no determination is made on partial signals. See
    decision.ExternalSourceUnavailableError and verify.LlmVerificationError.

    Security semantics (Feature 3): extracted document text is
    attacker-controlled, so it is scanned for prompt-injection payloads
    BEFORE reaching the LLM. Suspected payloads are sanitized out of the
    LLM input, logged to the audit trail, and force an extra
    prompt_injection_suspected mismatch so the merchant routes to human
    review.

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

    # --- Step 2: Prompt-injection defense (Feature 3) ---
    # The fields below come from OCR/vision extraction of documents the
    # MERCHANT uploaded — attacker-controlled input. Scan for known
    # instruction-override payloads BEFORE anything reaches the LLM, and
    # log a finding in the audit trail when one is suspected.
    import injection_guard

    injection_findings = injection_guard.scan_fields(fields_by_type)
    llm_input_fields = (
        injection_guard.sanitize_fields(fields_by_type, injection_findings)
        if injection_findings
        else fields_by_type
    )
    if injection_findings:
        detail = "; ".join(
            f"{f.document_type}/{f.field_name}: {f.pattern_label}"
            for f in injection_findings
        )
        db.add(AuditLog(
            merchant_id=merchant.id,
            action="prompt_injection_suspected",
            reason=f"Suspected prompt-injection payload in document text; fields sanitized before LLM: {detail}",
        ))

    # --- Step 3: LLM cross-document consistency check ---
    # The LLM is a REQUIRED signal, never optional. If it is unavailable
    # (real outage or the llm_down demo fault), verification is DEFERRED
    # — the merchant stays in 'submitted' and no determination is made on
    # partial signals. Continuing with external checks only could
    # silently approve a merchant whose cross-document inconsistency the
    # LLM was the only check able to catch.
    try:
        llm_result = verify.cross_verify_documents(llm_input_fields)
    except verify.LlmVerificationError as exc:
        db.add(AuditLog(
            merchant_id=merchant.id,
            action="verification_deferred",
            reason=f"LLM cross-verification unavailable; verification deferred (no determination made): {exc}",
        ))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification deferred: the LLM verification service is unavailable. No checks were run; retry once the service recovers.",
        )
    except Exception:
        logger.exception("LLM cross-verification crashed unexpectedly (not an outage)")
        raise

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

    # --- Step 4: External verification sources (all 5, no short-circuit) ---
    pan_fields = fields_by_type.get("PAN", {})
    bank_fields = fields_by_type.get("BANK_PROOF", {})
    pan_number = pan_fields.get("pan_number", "")
    account_number = bank_fields.get("account_number", "")

    try:
        external_breakdown = decision.check_external_sources(db, pan_number, account_number or None)
    except decision.ExternalSourceUnavailableError as exc:
        # Same deferral rule as the LLM: an unavailable source proves
        # nothing about the merchant. Never score a merchant against
        # silence.
        db.add(AuditLog(
            merchant_id=merchant.id,
            action="verification_deferred",
            reason=f"External verification sources unavailable; verification deferred (no determination made): {exc}",
        ))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification deferred: the external verification sources are unavailable. No checks were run; retry once the service recovers.",
        )

    # --- Step 4b: Fraud-ring check (cross-merchant shared identifiers) ---
    fraud_ring_breakdown = decision.check_shared_identifiers(db, merchant_id, pan_number, account_number or None)

    # --- Step 5: Merge all findings into one breakdown ---
    all_matched = (
        llm_matched
        + [cm.model_dump() for cm in external_breakdown.matched]
        + [cm.model_dump() for cm in fraud_ring_breakdown.matched]
    )
    all_mismatched = (
        llm_mismatched
        + [cm.model_dump() for cm in external_breakdown.mismatched]
        + [cm.model_dump() for cm in fraud_ring_breakdown.mismatched]
    )

    # A suspected prompt-injection payload is itself a mismatch: the
    # merchant must route to human review, never verify clean. The
    # sanitized fields were already sent to the LLM, so the payload never
    # influenced the consistency verdict.
    if injection_findings:
        all_mismatched.append({
            "check_name": "prompt_injection_suspected",
            "document_type": ", ".join(sorted({f.document_type for f in injection_findings})),
            "matched": False,
            "detail": "Document text contained a suspected prompt-injection payload; "
                       "content was withheld from the AI check and this merchant "
                       "was routed to human review.",
        })

    # Ensure matched field is always a bool (not a string from old data)
    for entry in all_matched:
        entry["matched"] = bool(entry["matched"])
    for entry in all_mismatched:
        entry["matched"] = bool(entry["matched"])

    # --- Step 6: Store on the Merchant row ---
    merchant.matched_checks = _json.dumps(all_matched)
    merchant.mismatched_checks = _json.dumps(all_mismatched)
    merchant.risk_score = _compute_risk_score(all_mismatched)

    if all_mismatched:
        merchant.rejection_cause = verify.generate_rejection_cause(all_mismatched)
        merchant.onboarding_status = "verified_mismatched"
    else:
        merchant.rejection_cause = None
        merchant.onboarding_status = "verified_matching"

    # Log the verification run for the audit trail (also persists any
    # prompt_injection_suspected entry added in Step 2)
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


@router.post("/maintenance/clear-test-merchants", response_model=MaintenanceResult)
def clear_test_merchants(
    db: Session = Depends(get_db),
    admin: Merchant = Depends(require_role("admin")),
) -> MaintenanceResult:
    """
    Admin-only maintenance: archives merchants created by E2E test runs so
    the /admin/batch-test accuracy report (and the admin queue) reads
    correctly on a live demo database.

    A merchant is considered test data when it has NO `expected_outcome`
    audit entry — the seeded ground-truth merchants all have one, and every
    test-run account (unique emails per run) does not. Archiving is a soft
    flag (Merchant.is_test=True): rows and audit trails are preserved, and
    the action itself is logged on the admin's own audit trail.
    """
    has_expected_outcome = sa_exists().where(
        AuditLog.merchant_id == Merchant.id,
        AuditLog.action == "expected_outcome",
    )
    test_merchants = db.query(Merchant).filter(
        Merchant.role == "merchant",
        Merchant.is_test == False,
        ~has_expected_outcome,
    ).all()

    archived_emails = [m.email for m in test_merchants]
    for merchant in test_merchants:
        merchant.is_test = True

    if test_merchants:
        db.add(AuditLog(
            merchant_id=admin.id,
            action="test_merchants_archived",
            reason=f"Archived {len(test_merchants)} E2E/test merchant(s) via maintenance action",
        ))
    db.commit()

    remaining = db.query(Merchant).filter(
        Merchant.role == "merchant", Merchant.is_test == False
    ).count()

    return MaintenanceResult(
        archived_count=len(test_merchants),
        archived_emails=archived_emails,
        remaining_count=remaining,
    )


@router.post("/batch-test", response_model=BatchTestReport)
def run_batch_test(
    db: Session = Depends(get_db),
    _admin: Merchant = Depends(require_role("admin")),
) -> BatchTestReport:
    """
    Reports accuracy across every non-archived merchant currently in the
    system. Archived test merchants (is_test=True) are excluded so the
    accuracy % is computed over scorable records only.
    Intended to be run against the seeded synthetic dataset (see
    seed.py) so judges can see measured accuracy, not just a live demo.

    Note: "correctness" here is derived from each seeded merchant's
    `expected_outcome` audit note written by seed.py, so this reflects
    ground truth built into the test data — not a guess.
    """
    merchants = db.query(Merchant).filter(
        Merchant.role == "merchant", Merchant.is_test == False
    ).all()
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


# ---------------------------------------------------------------------------
# Feature 1: demo failure-injection (chaos panel)
# ---------------------------------------------------------------------------
# Admin-only toggles that simulate real outages at the exact boundaries
# where they would occur (OCR engine, LLM API, external sources). The
# app code then exercises its REAL graceful-degradation paths — see
# faults.py for the full design rationale. Every toggle is written to
# the admin's audit trail so the demo itself is explainable.


def _fault_response(state: dict[str, bool]) -> FaultStateResponse:
    return FaultStateResponse(
        ocr_down=state["ocr_down"],
        llm_down=state["llm_down"],
        sources_down=state["sources_down"],
        active=[name for name, on in state.items() if on],
    )


@router.get("/faults", response_model=FaultStateResponse)
def get_fault_state(
    _admin: Merchant = Depends(require_role("admin")),
) -> FaultStateResponse:
    """Current state of the demo fault toggles (admin chaos panel)."""
    import faults

    return _fault_response(faults.snapshot())


@router.put("/faults/{fault_name}", response_model=FaultStateResponse)
def set_fault(
    fault_name: str,
    payload: FaultToggleRequest,
    db: Session = Depends(get_db),
    admin: Merchant = Depends(require_role("admin")),
) -> FaultStateResponse:
    """Enable or disable one demo fault (e.g. PUT /admin/faults/llm_down
    with {"enabled": true}). Writes the toggle to the admin's audit trail
    so the chaos demo is fully explainable.
    """
    import faults

    try:
        changed = faults.set_fault(fault_name, payload.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if changed:
        db.add(AuditLog(
            merchant_id=admin.id,
            action="demo_fault_toggled",
            reason=f"Demo fault '{fault_name}' {'enabled' if payload.enabled else 'cleared'} "
                   f"by {admin.email}",
        ))
        db.commit()
    return _fault_response(faults.snapshot())


@router.post("/faults/reset", response_model=FaultStateResponse)
def reset_faults(
    db: Session = Depends(get_db),
    admin: Merchant = Depends(require_role("admin")),
) -> FaultStateResponse:
    """Clears every demo fault at once — the panic button for the demo.
    Faults are process-local, so this is instant and cannot get stuck.
    """
    import faults

    cleared = faults.reset_all()
    if cleared:
        db.add(AuditLog(
            merchant_id=admin.id,
            action="demo_fault_toggled",
            reason=f"All demo faults cleared by {admin.email}: {', '.join(cleared)}",
        ))
        db.commit()
    return _fault_response(faults.snapshot())


# ---------------------------------------------------------------------------
# Feature 2: empirical risk-weight calibration
# ---------------------------------------------------------------------------


def _stats_response(stats) -> ClassScoreStatsResponse:
    return ClassScoreStatsResponse(
        count=stats.count,
        mean_score=stats.mean_score,
        min_score=stats.min_score,
        max_score=stats.max_score,
    )


def _report_response(report) -> RiskEvalReportResponse:
    """Maps risk_eval.RiskEvalReport dataclass -> API response schema."""
    return RiskEvalReportResponse(
        total_labeled=report.total_labeled,
        good_count=report.good_count,
        bad_count=report.bad_count,
        replayed_count=report.replayed_count,
        pipeline_scored_count=report.pipeline_scored_count,
        good_stats=_stats_response(report.good_stats),
        bad_stats=_stats_response(report.bad_stats),
        best_threshold=report.best_threshold,
        best_f1=report.best_f1,
        best_confusion=report.best_confusion,
        threshold_sweep=[
            ThresholdRowResponse(
                threshold=row.threshold,
                precision=row.precision,
                recall=row.recall,
                f1=row.f1,
                accuracy=row.accuracy,
                true_positives=row.true_positives,
                false_positives=row.false_positives,
                false_negatives=row.false_negatives,
                true_negatives=row.true_negatives,
            )
            for row in report.threshold_sweep
        ],
        weights_used=report.weights_used,
    )


@router.post("/risk-eval", response_model=RiskEvalReportResponse)
def run_risk_eval(
    db: Session = Depends(get_db),
    _admin: Merchant = Depends(require_role("admin")),
) -> RiskEvalReportResponse:
    """
    Runs the empirical risk-weight calibration report: scores every
    labeled merchant under the CURRENT weights and measures how well the
    risk score separates clean from flagged merchants (per-class score
    stats, best-F1 threshold, full cutoff sweep).

    This is the "how do you know your model is good?" answer: the
    weights are measured against the labeled set, not just reasoned
    about. See risk_eval.py for methodology and honest limitations.
    """
    import risk_eval

    return _report_response(risk_eval.evaluate(db))
