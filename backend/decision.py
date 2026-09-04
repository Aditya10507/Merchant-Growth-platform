"""
decision.py
-----------
The Decision Engine is the single source of truth for whether a
merchant's document is approved, flagged, or rejected. It combines
three independent signals:

  1. OCR confidence (was the document readable?)
  2. LLM cross-verification findings (are the fields internally consistent?)
  3. External verification results (do the 5 simulated data sources agree?)

This is intentionally rule-based, not LLM-based — see Architecture doc
section on Business Rules. Every decision writes a row to audit_logs so
the outcome can always be explained after the fact.
"""

from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session

from config import settings
from db import (
    AuditLog,
    AutomatedVerification,
    BankAccountValidation,
    CkycRecord,
    ComplianceReview,
    GovtDatabase,
)
from schemas import CheckResult, LlmVerificationResult, VerificationBreakdown


class Decision(str, Enum):
    APPROVED = "approved"
    FLAGGED = "flagged"
    REJECTED = "rejected"


class ExternalSourceUnavailableError(RuntimeError):
    """Raised when the simulated external verification sources are
    unavailable (demo fault: sources_down). Deliberately NOT a
    "mismatch": an unavailable source proves nothing about the
    merchant — callers must DEFER verification (see admin.py), never
    treat it as a failed check.
    """


def compute_risk_score(
    mismatched_checks: list[dict],
    weights: dict[str, int] | None = None,
    max_score: int | None = None,
) -> int:
    """Weighted sum of mismatched checks, capped at the max risk score.

    Single source of truth for risk scoring — used by the admin verify
    flow (admin.py), the empirical calibration report (risk_eval.py),
    and anything that needs to score a breakdown of checks.

    check_name values starting with 'llm_cross_check' all map to the flat
    'llm_cross_check' weight — every inconsistent field adds its own points.
    """
    from config import settings

    weights = weights if weights is not None else settings.RISK_WEIGHTS
    max_score = max_score if max_score is not None else settings.MAX_RISK_SCORE

    total = 0
    for check in mismatched_checks:
        check_name = check["check_name"]
        weight_key = "llm_cross_check" if check_name.startswith("llm_cross_check") else check_name
        total += weights.get(weight_key, 10)
    return min(total, max_score)


@dataclass(frozen=True)
class DecisionOutcome:
    decision: Decision
    reason: str


def check_external_sources(
    db: Session, pan_number: str, account_number: str | None
) -> VerificationBreakdown:
    """
    Phase 3 rewrite: checks ALL 5 external verification sources
    unconditionally (no short-circuiting) and returns a structured
    VerificationBreakdown listing every matched and mismatched check.

    Design change from the original version: the old implementation
    returned on the FIRST failure it found, so the admin could only
    ever see one problem at a time. The new version checks everything
    so the admin gets the full picture — e.g. "PAN failed government
    check AND bank account couldn't be validated" in one response.

    Missing records are treated as mismatches (not exceptions) — this
    is data, not an error. Each source maps to a document_type:
      - govt_database, ckyc_records, automated_verification,
        compliance_reviews → "PAN"
      - bank_account_validation → "BANK_PROOF"
    """
    matched: list[CheckResult] = []
    mismatched: list[CheckResult] = []

    # Demo fault hook (admin chaos panel): simulate an outage of the 5
    # external verification sources. Raises so admin.py DEFERS the whole
    # verification — an unavailable source is not evidence of a mismatch.
    import faults
    if faults.is_active("sources_down"):
        raise ExternalSourceUnavailableError(
            "Simulated outage of the external verification sources "
            "(demo fault: sources_down). No checks were run."
        )

    # --- 1. Government database ---
    govt = db.query(GovtDatabase).filter(GovtDatabase.pan_number == pan_number).first()
    if govt is None:
        mismatched.append(CheckResult(
            check_name="govt_database", document_type="PAN", matched=False,
            detail="PAN not found in government database",
        ))
    elif govt.status != "verified":
        mismatched.append(CheckResult(
            check_name="govt_database", document_type="PAN", matched=False,
            detail=f"Government database status is '{govt.status}' instead of 'verified'",
        ))
    else:
        matched.append(CheckResult(
            check_name="govt_database", document_type="PAN", matched=True,
            detail="PAN verified in government database",
        ))

    # --- 2. CKYC records ---
    ckyc = db.query(CkycRecord).filter(CkycRecord.pan_number == pan_number).first()
    if ckyc is None:
        mismatched.append(CheckResult(
            check_name="ckyc_records", document_type="PAN", matched=False,
            detail="No CKYC record found for this PAN",
        ))
    elif ckyc.kyc_status != "verified":
        mismatched.append(CheckResult(
            check_name="ckyc_records", document_type="PAN", matched=False,
            detail=f"CKYC status is '{ckyc.kyc_status}' instead of 'verified'",
        ))
    else:
        matched.append(CheckResult(
            check_name="ckyc_records", document_type="PAN", matched=True,
            detail="CKYC record verified",
        ))

    # --- 3. Automated verification ---
    auto_checks = db.query(AutomatedVerification).filter(
        AutomatedVerification.pan_number == pan_number
    ).all()
    if not auto_checks:
        mismatched.append(CheckResult(
            check_name="automated_verification", document_type="PAN", matched=False,
            detail="No automated verification records found for this PAN",
        ))
    else:
        failed_checks = [c for c in auto_checks if c.result != "pass"]
        if failed_checks:
            details = "; ".join(f"{c.check_type}: {c.result}" for c in failed_checks)
            mismatched.append(CheckResult(
                check_name="automated_verification", document_type="PAN", matched=False,
                detail=f"One or more automated checks failed: {details}",
            ))
        else:
            matched.append(CheckResult(
                check_name="automated_verification", document_type="PAN", matched=True,
                detail="All automated verification checks passed",
            ))

    # --- 4. Bank account validation ---
    if account_number:
        bank = db.query(BankAccountValidation).filter(
            BankAccountValidation.account_number == account_number
        ).first()
        if bank is None:
            mismatched.append(CheckResult(
                check_name="bank_account_validation", document_type="BANK_PROOF", matched=False,
                detail="Bank account not found in validation database",
            ))
        elif bank.verified != "yes":
            mismatched.append(CheckResult(
                check_name="bank_account_validation", document_type="BANK_PROOF", matched=False,
                detail=f"Bank account verification status is '{bank.verified}' (name match score: {bank.name_match_score})",
            ))
        else:
            matched.append(CheckResult(
                check_name="bank_account_validation", document_type="BANK_PROOF", matched=True,
                detail=f"Bank account verified (name match score: {bank.name_match_score})",
            ))
    else:
        mismatched.append(CheckResult(
            check_name="bank_account_validation", document_type="BANK_PROOF", matched=False,
            detail="No bank account number available for validation",
        ))

    # --- 5. Compliance review ---
    compliance = db.query(ComplianceReview).filter(
        ComplianceReview.pan_number == pan_number
    ).first()
    if compliance is None:
        # No compliance record is acceptable — not every PAN gets reviewed
        matched.append(CheckResult(
            check_name="compliance_reviews", document_type="PAN", matched=True,
            detail="No compliance flags on record for this PAN",
        ))
    elif compliance.status == "flagged":
        mismatched.append(CheckResult(
            check_name="compliance_reviews", document_type="PAN", matched=False,
            detail=f"Compliance review flagged: {compliance.flag_reason or 'no reason provided'}",
        ))
    else:
        matched.append(CheckResult(
            check_name="compliance_reviews", document_type="PAN", matched=True,
            detail="Compliance review clear",
        ))

    return VerificationBreakdown(matched=matched, mismatched=mismatched)


def check_shared_identifiers(
    db: Session, merchant_id: int, pan_number: str, account_number: str | None
) -> VerificationBreakdown:
    """
    Cross-merchant fraud-ring check: does this PAN or bank account number
    appear on any OTHER merchant's active documents? A shared identifier
    across unrelated applications is a strong fraud signal.

    Only active documents (is_active=True) are considered, so a
    restarted application's retired documents don't cause false positives.
    """
    from db import Document

    matched: list[CheckResult] = []
    mismatched: list[CheckResult] = []

    if pan_number:
        other_pan_merchants = (
            db.query(Document.merchant_id)
            .filter(
                Document.extracted_pan_number == pan_number,
                Document.merchant_id != merchant_id,
                Document.is_active == True,
            )
            .distinct()
            .all()
        )
        if other_pan_merchants:
            ids = ", ".join(str(m[0]) for m in other_pan_merchants)
            mismatched.append(CheckResult(
                check_name="fraud_ring_pan", document_type="PAN", matched=False,
                detail=f"This PAN also appears on merchant application(s): {ids}",
            ))
        else:
            matched.append(CheckResult(
                check_name="fraud_ring_pan", document_type="PAN", matched=True,
                detail="PAN is not shared with any other application",
            ))

    if account_number:
        other_bank_merchants = (
            db.query(Document.merchant_id)
            .filter(
                Document.extracted_account_number == account_number,
                Document.merchant_id != merchant_id,
                Document.is_active == True,
            )
            .distinct()
            .all()
        )
        if other_bank_merchants:
            ids = ", ".join(str(m[0]) for m in other_bank_merchants)
            mismatched.append(CheckResult(
                check_name="fraud_ring_bank", document_type="BANK_PROOF", matched=False,
                detail=f"This bank account also appears on merchant application(s): {ids}",
            ))
        else:
            matched.append(CheckResult(
                check_name="fraud_ring_bank", document_type="BANK_PROOF", matched=True,
                detail="Bank account is not shared with any other application",
            ))

    return VerificationBreakdown(matched=matched, mismatched=mismatched)


def evaluate(
    ocr_confidence: float,
    llm_result: LlmVerificationResult | None,
    pan_number: str,
    account_number: str | None,
    db: Session,
) -> DecisionOutcome:
    """
    Phase 3 note: this function is now ONLY used for the per-document
    OCR-confidence-too-low instant rejection path at upload time.
    The LLM cross-check and external source checks have been moved to
    the admin-triggered verify endpoint (admin.py) and return structured
    VerificationBreakdown instead of a single DecisionOutcome.

    This function retains the original short-circuiting behavior because
    OCR confidence is a per-document, per-upload check — not part of the
    cross-document verification pipeline.
    """
    if ocr_confidence < settings.MIN_OCR_CONFIDENCE:
        return DecisionOutcome(
            Decision.REJECTED,
            f"OCR confidence {ocr_confidence:.2f} below minimum threshold {settings.MIN_OCR_CONFIDENCE}; please re-upload a clearer document",
        )

    if llm_result is None:
        # LLM call failed entirely (see verify.py) — never silently approve.
        return DecisionOutcome(Decision.FLAGGED, "Automated cross-verification unavailable; routed to manual review")

    if not llm_result.overall_consistent:
        inconsistent = [f.field_name for f in llm_result.findings if not f.consistent]
        return DecisionOutcome(
            Decision.FLAGGED,
            f"Cross-verification found inconsistencies in: {', '.join(inconsistent) or 'unspecified fields'}",
        )

    if not pan_number:
        return DecisionOutcome(Decision.REJECTED, "PAN number could not be extracted from the document")

    # Phase 3: external checks are now admin-triggered only. This path
    # is reached when OCR confidence is fine, LLM found no issues, and
    # PAN number was extracted — return a clean approval for the upload
    # record. The full external check happens when the admin triggers
    # verification via POST /admin/merchants/{id}/verify.
    return DecisionOutcome(Decision.APPROVED, "Document passed OCR and LLM checks; pending admin verification")


def log_decision(
    db: Session,
    merchant_id: int,
    document_id: int | None,
    outcome: DecisionOutcome,
) -> None:
    """Writes an immutable audit trail entry for the decision that was made."""
    entry = AuditLog(
        merchant_id=merchant_id,
        document_id=document_id,
        action=outcome.decision.value,
        reason=outcome.reason,
    )
    db.add(entry)
    db.commit()
