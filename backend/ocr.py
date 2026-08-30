"""
ocr.py
------
Wraps OCR.space API so the rest of the app never touches the OCR library
directly (Dependency Inversion — callers depend on this module's small
interface, not on the OCR.space API). This also makes it possible to swap
the OCR engine later without touching any calling code.

extract_text() returns the raw detected text lines and an overall
confidence score. Turning that raw text into typed fields (pan_number,
name, dob, etc.) is a separate, per-document-type parsing step below,
since that logic is specific to each document type and not an OCR concern.

Setup:
  1. Get a free API key at https://ocr.space/ocrapi/freekey (no credit card)
  2. Set OCR_API_KEY in backend/.env
  3. Free tier: 25,000 requests/month
"""

import os
import re
import base64
import time
import threading
from dataclasses import dataclass
from functools import lru_cache

import requests

from config import settings

logger = __import__("logging").getLogger(__name__)


class OcrRateLimiter:
    """Enforces a minimum delay between OCR API calls to stay within
    OCR.space's free-tier rate limit (~1 req/sec). Thread-safe."""

    def __init__(self, min_interval: float = 1.0):
        self._min_interval = min_interval
        self._last_call: float = 0.0
        self._lock = threading.Lock()

    def wait_if_needed(self) -> None:
        """Sleep if necessary to respect the rate limit before the next call."""
        with self._lock:
            now = time.time()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_call = time.time()


# One rate limiter shared across all background OCR tasks.
# 1.0s minimum interval keeps us safely within OCR.space's free-tier limit.
_RATE_LIMITER = OcrRateLimiter(min_interval=1.0)


OCR_API_URL = "https://api.ocr.space/parse/image"


@dataclass(frozen=True)
class OcrResult:
    raw_lines: list[str]
    confidence: float  # average confidence across detected text lines


class OcrEngineError(RuntimeError):
    """Raised when the OCR engine fails to process a document."""


def _get_api_key() -> str:
    """Returns the OCR.space API key from config or environment."""
    key = getattr(settings, "OCR_API_KEY", "") or os.getenv("OCR_API_KEY", "")
    if not key:
        raise OcrEngineError(
            "OCR_API_KEY is not set. Get a free key at https://ocr.space/ocrapi/freekey "
            "and add it to backend/.env as OCR_API_KEY=your_key_here"
        )
    return key


def extract_text(file_path: str) -> OcrResult:
    """Runs OCR on a document image/PDF page and returns detected text + confidence."""
    api_key = _get_api_key()

    try:
        with open(file_path, "rb") as f:
            file_content = f.read()
    except FileNotFoundError:
        raise OcrEngineError(f"File not found: {file_path}")
    except Exception as exc:
        raise OcrEngineError(f"Failed to read file {file_path}: {exc}") from exc

    # Determine if the file is a PDF or image
    is_pdf = file_content[:4] == b"%PDF"

    def _call_ocr_space(ocr_engine: str):
        """Helper to call OCR.space with a specific engine."""
        if is_pdf:
            b64_content = base64.b64encode(file_content).decode("utf-8")
            return requests.post(
                OCR_API_URL,
                data={
                    "apikey": api_key,
                    "base64Image": f"data:application/pdf;base64,{b64_content}",
                    "language": "eng",
                    "isOverlayRequired": "false",
                    "OCREngine": ocr_engine,
                },
                timeout=30,
            )
        else:
            return requests.post(
                OCR_API_URL,
                files={"file": (os.path.basename(file_path), open(file_path, "rb"), "image/png")},
                data={
                    "apikey": api_key,
                    "language": "eng",
                    "isOverlayRequired": "false",
                    "OCREngine": ocr_engine,
                },
                timeout=30,
            )

    # Wait for rate limiter before making the API call
    _RATE_LIMITER.wait_if_needed()

    try:
        # Try Engine 2 first (better for printed documents), fallback to Engine 1
        response = _call_ocr_space("2")
        try:
            result_check = response.json()
            if result_check.get("IsErroredOnProcessing"):
                error_msg = result_check.get("ErrorMessage", [""])
                if isinstance(error_msg, list):
                    error_msg = ", ".join(error_msg)
                if "too small" in error_msg.lower():
                    logger.info("Engine 2 failed for %s (%s), falling back to Engine 1", file_path, error_msg)
                    _RATE_LIMITER.wait_if_needed()
                    response = _call_ocr_space("1")
        except Exception:
            pass  # If we can't parse JSON, just use the original response
    except requests.Timeout:
        raise OcrEngineError(f"OCR.space API timeout for {file_path}")
    except requests.ConnectionError:
        raise OcrEngineError("OCR.space API connection failed. Check your internet connection.")
    except Exception as exc:
        raise OcrEngineError(f"OCR.space API request failed for {file_path}: {exc}") from exc

    try:
        result = response.json()
    except Exception:
        raise OcrEngineError(f"OCR.space returned invalid JSON for {file_path}")

    # Check for API errors
    if result.get("IsErroredOnProcessing"):
        error_msg = result.get("ErrorMessage", ["Unknown error"])
        if isinstance(error_msg, list):
            error_msg = ", ".join(error_msg)
        raise OcrEngineError(f"OCR.space error for {file_path}: {error_msg}")

    # Check for parsed results
    parsed_results = result.get("ParsedResults")
    if not parsed_results:
        return OcrResult(raw_lines=[], confidence=0.0)

    # Extract text from the first parsed result
    parsed = parsed_results[0]
    raw_text = parsed.get("ParsedText", "")
    confidence = parsed.get("FileParseExitCode", 0)

    # ParseExitCode: 1 = success, others = partial/failed
    # Convert to a 0-1 confidence score
    avg_confidence = 0.95 if confidence == 1 else 0.7 if confidence == 0 else 0.0

    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

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
    typically an all-letters line of 2+ words that is NOT a document
    title or label. This is intentionally simple — the LLM cross-
    verification step is the authority on whether the extracted name
    is trustworthy, not this heuristic.
    """
    # Lines to skip — these are document titles/labels, not names
    skip_patterns = [
        "SAMPLE", "TEST DOCUMENT", "NOT A REAL",
        "PAN CARD", "GST", "BANK", "CERTIFICATE",
        "PROOF", "REGISTRATION", "ACCOUNT",
        "Name:", "PAN Number:", "Date of Birth:",
        "IFSC", "Account Number:", "Account Holder:",
    ]
    for line in lines:
        stripped = line.strip()
        # Skip empty lines, lines with colons (labels), and document titles
        if not stripped or ":" in stripped:
            continue
        # Skip lines containing title words
        if any(word.upper() in stripped.upper() for word in skip_patterns):
            continue
        words = stripped.split()
        if len(words) >= 2 and all(word.isalpha() for word in words):
            return stripped
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
