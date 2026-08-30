"""
ocr.py
------
Wraps PaddleOCR so the rest of the app never touches the OCR library
directly (Dependency Inversion — callers depend on this module's small
interface, not on PaddleOCR's API). This also makes it possible to swap
the OCR engine later without touching any calling code.

extract_text() returns the raw detected text lines and an overall
confidence score. Turning that raw text into typed fields (pan_number,
name, dob, etc.) is a separate, per-document-type parsing step below,
since that logic is specific to each document type and not an OCR concern.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from config import settings


@dataclass(frozen=True)
class OcrResult:
    raw_lines: list[str]
    confidence: float  # average confidence across detected text lines


class OcrEngineError(RuntimeError):
    """Raised when the OCR engine fails to process a document."""


@lru_cache(maxsize=1)
def _get_engine():
    """
    Lazily initializes PaddleOCR once per process (model loading is
    expensive, and on first run downloads model weights from the
    internet — this can be slow or fail entirely without connectivity).
    Import is deferred so the rest of the app can be tested without the
    heavy PaddleOCR/PaddlePaddle dependency installed.
    """
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise OcrEngineError(
            "PaddleOCR is not installed. Run `pip install -r requirements.txt`."
        ) from exc

    try:
        return PaddleOCR(use_angle_cls=True, lang="en")
    except Exception as exc:
        # Model download/initialization can fail for many reasons (no
        # internet on first run, corrupted cache, incompatible
        # paddlepaddle build). Whatever the cause, surface it as a
        # single well-known error type so callers can always handle it
        # and never leave a document stuck mid-processing.
        raise OcrEngineError(
            f"PaddleOCR failed to initialize: {exc}. "
            "If this is the first run, it may be downloading model weights — "
            "check your internet connection and try again."
        ) from exc


def extract_text(file_path: str) -> OcrResult:
    """Runs OCR on a document image/PDF page and returns detected text + confidence."""
    engine = _get_engine()

    try:
        result = engine.ocr(file_path, cls=True)
    except Exception as exc:  # OCR engine failures are treated as recoverable
        raise OcrEngineError(f"OCR processing failed for {file_path}: {exc}") from exc

    if not result or not result[0]:
        return OcrResult(raw_lines=[], confidence=0.0)

    lines: list[str] = []
    confidences: list[float] = []
    for detection in result[0]:
        _, (text, confidence) = detection
        lines.append(text)
        confidences.append(confidence)

    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return OcrResult(raw_lines=lines, confidence=avg_confidence)


# ---------------------------------------------------------------------------
# Document-type-specific field parsing
# ---------------------------------------------------------------------------


def parse_pan_fields(ocr: OcrResult) -> dict[str, str]:
    """Extracts PAN number, name, and DOB from raw OCR text lines."""
    joined = " ".join(ocr.raw_lines)
    pan_match = re.search(r"[A-Z]{5}[0-9]{4}[A-Z]", joined)
    dob_match = re.search(r"\d{2}[/-]\d{2}[/-]\d{4}", joined)

    return {
        "pan_number": pan_match.group(0) if pan_match else "",
        # Name extraction from unstructured OCR text is inherently noisy;
        # the LLM verification step (verify.py) is responsible for
        # judging plausibility, not this parser.
        "name": _best_guess_name_line(ocr.raw_lines),
        "dob": dob_match.group(0) if dob_match else "",
    }


def parse_gst_fields(ocr: OcrResult) -> dict[str, str]:
    joined = " ".join(ocr.raw_lines)
    gst_match = re.search(settings.GST_REGEX.strip("^$"), joined)
    return {
        "gst_number": gst_match.group(0) if gst_match else "",
        "name": _best_guess_name_line(ocr.raw_lines),
    }


def parse_bank_proof_fields(ocr: OcrResult) -> dict[str, str]:
    joined = " ".join(ocr.raw_lines)
    ifsc_match = re.search(r"[A-Z]{4}0[A-Z0-9]{6}", joined)
    account_match = re.search(r"\b\d{9,18}\b", joined)
    return {
        "ifsc": ifsc_match.group(0) if ifsc_match else "",
        "account_number": account_match.group(0) if account_match else "",
        "name": _best_guess_name_line(ocr.raw_lines),
    }


def _best_guess_name_line(lines: list[str]) -> str:
    """
    Heuristic: the merchant/holder name on Indian KYC documents is
    typically an all-letters line of 2+ words. This is intentionally
    simple — the LLM cross-verification step is the authority on
    whether the extracted name is trustworthy, not this heuristic.
    """
    for line in lines:
        words = line.strip().split()
        if len(words) >= 2 and all(word.isalpha() for word in words):
            return line.strip()
    return ""


FIELD_PARSERS = {
    "PAN": parse_pan_fields,
    "GST": parse_gst_fields,
    "BANK_PROOF": parse_bank_proof_fields,
}


def extract_structured_fields(file_path: str, doc_type: str) -> tuple[dict[str, str], float]:
    """Full pipeline: OCR the file, then parse fields for the given document type."""
    if doc_type not in FIELD_PARSERS:
        raise ValueError(f"Unsupported document type: {doc_type}")

    ocr_result = extract_text(file_path)
    fields = FIELD_PARSERS[doc_type](ocr_result)
    return fields, ocr_result.confidence