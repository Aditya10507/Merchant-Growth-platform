"""
documents.py
------------
Endpoints for uploading a KYC document and checking verification status.

Flow per upload (mirrors the Architecture doc's data-flow section):
  1. Validate file type/size and that the document matches the expected
     slot type (server-side safety net; the frontend also does this
     check before the file is even sent).
  2. Immediately save document as "verifying" and return the response
     so the frontend is never blocked.
  3. Run OCR + format matching in a background task (FastAPI BackgroundTasks)
     so the upload endpoint returns in <1 second regardless of OCR speed.
  4. If OCR finds a format mismatch → mark document as "invalid_format".
  5. If all 3 required documents have passed OCR → run LLM cross-verification
     + the Decision Engine.

This architecture ensures:
  - The frontend never times out waiting for OCR (which can take 10-30s on CPU).
  - Invalid documents are caught quickly via format matching.
  - The merchant sees real-time status updates via polling.
"""

import json as _json
import logging
import re
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from auth import get_current_merchant
from config import settings
from db import AuditLog, Document, Merchant, SessionLocal, get_db
import decision
import ocr
from schemas import DocumentStatusResponse, MerchantStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# Semaphore to serialize OCR processing — PaddleOCR exhausts GPU/CPU
# tensor memory when multiple background tasks run concurrently, causing
# crashes like "Tensor holds no memory". Limiting to 1 OCR task at a
# time prevents this while still keeping the upload endpoint fast
# (it returns immediately; only the background OCR is serialized).
_OCR_SEMAPHORE = threading.Semaphore(1)

# A quick heuristic signature per document type used to catch an obviously
# wrong document (e.g. Aadhaar uploaded into the PAN slot) before running
# the full OCR/LLM pipeline. This is a fast pre-check, not the final word —
# the Decision Engine still runs the authoritative checks afterward.
_TYPE_SIGNATURES: dict[str, re.Pattern] = {
    "PAN": re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]"),
    "GST": re.compile(settings.GST_REGEX.strip("^$")),
    "BANK_PROOF": re.compile(r"[A-Z]{4}0[A-Z0-9]{6}"),  # IFSC present
}


def _validate_upload(file: UploadFile) -> None:
    """Validates file content type against the allowed list."""
    if file.content_type not in settings.ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: {settings.ALLOWED_CONTENT_TYPES}",
        )


def _save_upload(file: UploadFile, merchant_id: int, doc_type: str) -> str:
    """Saves the uploaded file to disk and returns the file path."""
    # Ensure the upload directory exists before writing
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    extension = Path(file.filename or "").suffix or ".bin"
    filename = f"{merchant_id}_{doc_type}_{uuid.uuid4().hex}{extension}"
    destination = settings.UPLOAD_DIR / filename

    contents = file.file.read()
    if len(contents) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)}MB",
        )

    destination.write_bytes(contents)
    return str(destination)


# ---------------------------------------------------------------------------
# Background OCR processing — runs after the upload response is sent
# ---------------------------------------------------------------------------

def _process_document_ocr(document_id: int, file_path: str, doc_type: str, merchant_id: int) -> None:
    """Background task entry point — acquires the OCR semaphore to
    serialize processing, then delegates to the actual OCR worker."""
    with _OCR_SEMAPHORE:
        _run_ocr(document_id, file_path, doc_type, merchant_id)


def _run_ocr(document_id: int, file_path: str, doc_type: str, merchant_id: int) -> None:
    """
    Background task that runs OCR on an uploaded document, checks the
    extracted format against expected signatures, and either marks the
    document as invalid_format or stores the fields and triggers
    cross-document verification if all required docs are now present.

    Creates its own DB session since BackgroundTasks run after the
    request's session is closed.
    """
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if document is None:
            logger.error("Background OCR: document %s not found", document_id)
            return

        # Step 1: Run OCR to extract fields from the document image
        try:
            fields, confidence = ocr.extract_structured_fields(file_path, doc_type)
        except (ocr.OcrEngineError, ValueError) as exc:
            logger.warning("OCR failed for document %s: %s", document_id, exc)
            document.verification_status = "rejected"
            document.rejection_reason = str(exc)
            db.commit()
            decision.log_decision(
                db, merchant_id, document_id,
                decision.DecisionOutcome(decision.Decision.REJECTED, str(exc)),
            )
            return
        except Exception as exc:
            logger.exception("Unexpected error during OCR for document %s", document_id)
            document.verification_status = "rejected"
            document.rejection_reason = "Verification service encountered an unexpected error. Please try re-uploading."
            db.commit()
            decision.log_decision(
                db, merchant_id, document_id,
                decision.DecisionOutcome(decision.Decision.REJECTED, f"Unexpected OCR error: {exc}"),
            )
            return

        # Step 2: Format matching — does the extracted content match the
        # expected document type's signature? Uses invalid_format (not
        # rejected) so the merchant can retry without restarting.
        signature = _TYPE_SIGNATURES.get(doc_type)
        joined_text = " ".join(fields.values())
        if signature and not signature.search(joined_text):
            reason = f"Uploaded file does not appear to be a valid {doc_type.replace('_', ' ').title()} document"
            document.verification_status = "invalid_format"
            document.rejection_reason = reason
            db.commit()
            decision.log_decision(
                db, merchant_id, document_id,
                decision.DecisionOutcome(decision.Decision.REJECTED, reason),
            )
            logger.info("Document %s format mismatch: %s", document_id, reason)
            return

        # Step 3: Format matched — store extracted fields and OCR confidence
        document.extracted_fields_json = _json.dumps(fields)
        document.ocr_confidence = confidence
        # Populate indexed columns for cross-merchant fraud-ring lookups
        if doc_type == "PAN":
            document.extracted_pan_number = fields.get("pan_number") or None
        elif doc_type == "BANK_PROOF":
            document.extracted_account_number = fields.get("account_number") or None
        document.verification_status = "verifying"
        db.commit()

        logger.info("Document %s passed format check, fields stored", document_id)

        # Step 4: If all 3 required document types are now present, trigger
        # cross-document verification + the Decision Engine.
        merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
        if merchant is not None:
            _run_verification_if_ready(merchant, db)

    except Exception:
        # Safety net: never leave a document stuck at "verifying" forever
        logger.exception("Unexpected error in background OCR task for document %s", document_id)
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc and doc.verification_status == "verifying":
                doc.verification_status = "flagged"
                doc.rejection_reason = "Automated verification encountered an unexpected error; routed to manual review."
                db.commit()
        except Exception:
            logger.exception("Failed to update document %s after background error", document_id)
    finally:
        db.close()


def _run_verification_if_ready(merchant: Merchant, db: Session) -> None:
    """
    Phase 3 rewrite: this function now ONLY checks whether all 3 required
    document types have been uploaded and passed their instant format check.
    If so, it sets onboarding_status to "submitted" and marks each document
    as "submitted" — nothing more.

    The LLM cross-verification and the 5 simulated external source checks
    have been REMOVED from this automatic flow. They now happen on-demand
    when an admin clicks "Verify with internal databases" in the admin
    panel (admin.py's verify_application endpoint). This gives the admin
    control over when verification runs and ensures they see the full,
    structured breakdown (not a single aggregate recommendation).

    Only considers active documents (is_active=True) so restarted
    applications' retired documents don't interfere with the current flow.
    """
    documents = db.query(Document).filter(
        Document.merchant_id == merchant.id, Document.is_active == True
    ).all()
    uploaded_types = {d.doc_type for d in documents if d.extracted_fields_json}
    if uploaded_types != set(settings.SUPPORTED_DOCUMENT_TYPES):
        return  # still waiting on other documents

    logger.info("All documents present for merchant %s, marking as submitted", merchant.id)

    for document in documents:
        document.verification_status = "submitted"
    merchant.onboarding_status = "submitted"
    db.commit()

    logger.info("Merchant %s submitted — awaiting admin-triggered verification", merchant.id)


def _to_response(document: Document) -> DocumentStatusResponse:
    """Maps a Document ORM model to its API response shape."""
    return DocumentStatusResponse(
        id=document.id,
        doc_type=document.doc_type,
        verification_status=document.verification_status,
        ocr_confidence=document.ocr_confidence,
        extracted_fields=_json.loads(document.extracted_fields_json) if document.extracted_fields_json else None,
        rejection_reason=document.rejection_reason,
    )


# ---------------------------------------------------------------------------
# Upload endpoint — returns instantly, OCR runs in background
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=DocumentStatusResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    doc_type: str,
    file: UploadFile,
    merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
) -> DocumentStatusResponse:
    """
    Upload endpoint that returns immediately. The heavy OCR processing
    runs in a background thread so the frontend never times out.
    Using threading.Thread instead of FastAPI BackgroundTasks because
    BackgroundTasks are unreliable on Render free tier (the process can
    be suspended between requests, killing pending background tasks).

    Flow:
      1. Validate inputs (fast, synchronous)
      2. Save file to disk (fast, synchronous)
      3. Create document record with status "verifying" (fast, synchronous)
      4. Return response immediately (< 1 second total)
      5. Background thread: run OCR → format check → store fields → trigger verification
    """
    # Block uploads into a rejected application — merchant must restart first.
    if merchant.onboarding_status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This application was rejected. Please start a new application before uploading documents.",
        )
    # Block uploads once the application is submitted and awaiting admin
    # review — re-uploading mid-review could contradict what the admin
    # is looking at. A rejected application can still restart (above).
    if merchant.onboarding_status == "submitted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Your documents have already been submitted and are awaiting review.",
        )

    if doc_type not in settings.SUPPORTED_DOCUMENT_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown document type '{doc_type}'")

    _validate_upload(file)
    file_path = _save_upload(file, merchant.id, doc_type)

    # Create the document record immediately with "verifying" status.
    # The actual OCR processing happens in the background.
    document = Document(
        merchant_id=merchant.id,
        doc_type=doc_type,
        file_path=file_path,
        verification_status="verifying",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # Schedule OCR processing in a background thread — the endpoint returns
    # immediately and the frontend sees "verifying" via polling.
    # Using threading.Thread instead of FastAPI BackgroundTasks because
    # BackgroundTasks don't survive process suspension on Render free tier.
    t = threading.Thread(
        target=_process_document_ocr,
        args=(document.id, file_path, doc_type, merchant.id),
        daemon=True,
    )
    t.start()

    return _to_response(document)


@router.post("/restart-application", response_model=MerchantStatusResponse)
def restart_application(
    merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
) -> MerchantStatusResponse:
    """
    Allows a rejected merchant to start a completely new application.
    Old documents are soft-retired (is_active=False) and preserved
    for the audit trail; the merchant status resets to "pending".
    """
    if merchant.onboarding_status != "rejected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a rejected application can be restarted",
        )

    # Soft-retire all active documents — keep them for audit, but
    # they no longer count toward the current application.
    active_docs = db.query(Document).filter(
        Document.merchant_id == merchant.id, Document.is_active == True
    ).all()
    for doc in active_docs:
        doc.is_active = False

    merchant.onboarding_status = "pending"
    merchant.rejection_reason = None
    db.add(AuditLog(
        merchant_id=merchant.id,
        action="application_restarted",
        reason="Merchant started a new application after rejection",
    ))
    db.commit()

    return MerchantStatusResponse(
        merchant_id=merchant.id,
        onboarding_status=merchant.onboarding_status,
        rejection_reason=None,
        documents=[],
    )


@router.get("/status/{document_id}", response_model=DocumentStatusResponse)
def get_document_status(
    document_id: int,
    merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
) -> DocumentStatusResponse:
    """Returns the current status of a single document."""
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.merchant_id == merchant.id,
        Document.is_active == True,
    ).first()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return _to_response(document)


@router.get("/merchant-status", response_model=MerchantStatusResponse)
def get_merchant_status(
    merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
) -> MerchantStatusResponse:
    """Returns the merchant's onboarding status and all active documents."""
    documents = db.query(Document).filter(
        Document.merchant_id == merchant.id, Document.is_active == True
    ).all()
    return MerchantStatusResponse(
        merchant_id=merchant.id,
        onboarding_status=merchant.onboarding_status,
        rejection_reason=merchant.rejection_reason,
        documents=[_to_response(d) for d in documents],
    )
