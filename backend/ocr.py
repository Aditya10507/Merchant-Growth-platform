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

--- Reliability fix (Session 17) ---
Session 16's investigation confirmed OCR.space's free tier intermittently
returns an EMPTY result for a perfectly valid document — the same file
(UJALK5542W) passed in one test batch and failed in another, with no
rate-limit violation either time. That means "empty OCR response" and
"genuinely bad document" are NOT the same thing, and treating them as
the same thing (as the code previously did) causes valid documents to
be wrongly rejected.

This version fixes that by:
  1. Retrying up to 3 times with exponential backoff (2s, 4s, 8s) whenever
     OCR.space returns an empty/errored result, before giving up. This
     alone recovers most of the intermittent failures Session 16 found.
  2. Raising a NEW, distinct exception (OcrTemporarilyUnavailableError)
     when the document is STILL empty after all retries — separate from
     OcrEngineError's other cases (missing API key, file not found,
     network failure). Callers (documents.py) should catch this
     specifically and show the merchant "verification temporarily
     unavailable, please try again" instead of a hard "invalid document"
     rejection — a real, if unlikely, service outage should never look
     like the merchant did something wrong.
  3. Increasing the rate limiter's minimum interval from 1.0s to 2.0s.
     This does not fully prevent empty responses (Session 16 confirmed
     they happen even with delays) but it does reduce how often the
     free-tier rate limit itself gets hit, which compounds the problem.

Honest limitation: this cannot make failures impossible — OCR.space's
free tier is inherently unreliable under load, and no amount of retry
logic changes that. It makes failures rare and recoverable rather than
guaranteed. The reliable fix is upgrading off the free tier (see
session_log.md's Session 16 notes) — this is the best mitigation
available without a billing change.
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

    def __init__(self, min_interval: float = 2.0):
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


# One rate limiter shared across all OCR tasks. Increased from 1.0s to
# 2.0s — see the "Reliability fix" note above. This reduces how often we
# hit OCR.space's free-tier rate limit; it does not eliminate empty
# responses on its own, which is why the retry logic below also exists.
_RATE_LIMITER = OcrRateLimiter(min_interval=2.0)

# Retry configuration for intermittent empty OCR.space responses.
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = [2.0, 4.0, 8.0]  # delay BEFORE attempts 2, 3, 4 respectively (unused entries ignored)

OCR_API_URL = "https://api.ocr.space/parse/image"


@dataclass(frozen=True)
class OcrResult:
    raw_lines: list[str]
    confidence: float  # average confidence across detected text lines


class OcrEngineError(RuntimeError):
    """Raised when the OCR engine fails to process a document for a
    reason that is NOT a transient service hiccup — e.g. missing API
    key, unreadable file, network failure, or a genuine OCR.space error
    response. These are not worth retrying."""


class OcrTemporarilyUnavailableError(OcrEngineError):
    """
    Raised when OCR.space returned an empty/unusable result on every
    retry attempt. This is deliberately a DIFFERENT exception from
    OcrEngineError's other cases: it means "the service didn't cooperate
    right now," not "this document is invalid." Callers should show the
    merchant a retry-friendly message, not an "invalid document" rejection.
    """


def _get_api_key() -> str:
    """Returns the OCR.space API key from config or environment."""
    key = settings.OCR_API_KEY
    if not key:
        raise OcrEngineError(
            "OCR_API_KEY is not set. Get a free key at https://ocr.space/ocrapi/freekey "
            "and add it as an environment variable: OCR_API_KEY=your_key_here"
        )
    return key


def _call_ocr_space(file_path: str, file_content: bytes, is_pdf: bool, api_key: str, ocr_engine: str):
    """Makes a single HTTP call to OCR.space with the given engine. No retry logic here — that lives in extract_text()."""
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


def _attempt_once(file_path: str, file_content: bytes, is_pdf: bool, api_key: str) -> dict:
    """
    Performs one full OCR.space attempt (including the existing Engine 2
    -> Engine 1 fallback for "too small" errors) and returns the parsed
    JSON response. Raises OcrEngineError for non-retryable failures
    (timeout, connection error, invalid JSON). Does NOT decide whether an
    empty result should be retried — that decision lives in extract_text(),
    since only it knows how many attempts have already been made.
    """
    try:
        logger.info("Calling OCR.space Engine 2 for %s", file_path)
        response = _call_ocr_space(file_path, file_content, is_pdf, api_key, "2")
        try:
            result_check = response.json()
            if result_check.get("IsErroredOnProcessing"):
                error_msg = result_check.get("ErrorMessage", [""])
                if isinstance(error_msg, list):
                    error_msg = ", ".join(error_msg)
                if "too small" in error_msg.lower():
                    logger.info("Engine 2 failed for %s (%s), falling back to Engine 1", file_path, error_msg)
                    _RATE_LIMITER.wait_if_needed()
                    response = _call_ocr_space(file_path, file_content, is_pdf, api_key, "1")
        except Exception:
            pass  # If we can't parse JSON here, fall through to the main parse below (and its own error handling).
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

    logger.info(
        "OCR.space response for %s: HTTP=%d, IsErrored=%s, ParsedResults=%s",
        file_path,
        response.status_code,
        result.get("IsErroredOnProcessing"),
        len(result.get("ParsedResults", [])),
    )
    if "ParsedResults" in result:
        for i, pr in enumerate(result["ParsedResults"]):
            logger.info(
                "OCR.space ParsedResults[%d]: ExitCode=%s, TextPreview=%s",
                i,
                pr.get("FileParseExitCode"),
                pr.get("ParsedText", "")[:500] if pr.get("ParsedText") else "(empty)",
            )
    logger.info("OCR.space full response keys: %s", list(result.keys()))

    return result


def _is_empty_result(result: dict) -> bool:
    """True if this OCR.space response has no usable text — the case we retry."""
    if result.get("IsErroredOnProcessing"):
        return True
    parsed_results = result.get("ParsedResults")
    if not parsed_results:
        return True
    raw_text = parsed_results[0].get("ParsedText", "")
    return not raw_text.strip()


def extract_text(file_path: str) -> OcrResult:
    """
    Runs OCR on a document image/PDF page and returns detected text +
    confidence. Retries up to _MAX_ATTEMPTS times with exponential
    backoff if OCR.space returns an empty/errored result — see the
    "Reliability fix" note at the top of this file for why.

    Raises OcrTemporarilyUnavailableError (not a plain OcrEngineError) if
    every attempt comes back empty, so callers can distinguish "the
    service didn't cooperate" from "this document is genuinely invalid."
    """
    api_key = _get_api_key()

    try:
        with open(file_path, "rb") as f:
            file_content = f.read()
    except FileNotFoundError:
        raise OcrEngineError(f"File not found: {file_path}")
    except Exception as exc:
        raise OcrEngineError(f"Failed to read file {file_path}: {exc}") from exc

    is_pdf = file_content[:4] == b"%PDF"
    file_size = len(file_content)
    file_header = file_content[:8].hex()

    logger.info(
        "OCR request: file=%s, size=%d bytes, is_pdf=%s, header=%s",
        file_path, file_size, is_pdf, file_header,
    )

    result: dict = {}
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        _RATE_LIMITER.wait_if_needed()
        result = _attempt_once(file_path, file_content, is_pdf, api_key)

        if not _is_empty_result(result):
            break  # Got usable text — stop retrying.

        if attempt < _MAX_ATTEMPTS:
            backoff = _RETRY_BACKOFF_SECONDS[attempt - 1]
            logger.warning(
                "OCR.space returned an empty result for %s on attempt %d/%d — "
                "retrying in %.0fs (see Session 16: this is a known intermittent "
                "service issue, not necessarily a bad document).",
                file_path, attempt, _MAX_ATTEMPTS, backoff,
            )
            time.sleep(backoff)
        else:
            logger.error(
                "OCR.space returned an empty result for %s on all %d attempts. "
                "Full last response: %s",
                file_path, _MAX_ATTEMPTS, str(result)[:1000],
            )

    # If we exhausted every attempt and still have nothing usable, this is
    # a service-availability problem, not a document-quality problem —
    # raise the distinct exception so callers don't hard-reject the merchant.
    if _is_empty_result(result):
        if result.get("IsErroredOnProcessing"):
            error_msg = result.get("ErrorMessage", ["Unknown error"])
            if isinstance(error_msg, list):
                error_msg = ", ".join(error_msg)
            raise OcrTemporarilyUnavailableError(
                f"OCR.space could not process {file_path} after {_MAX_ATTEMPTS} attempts: {error_msg}"
            )
        raise OcrTemporarilyUnavailableError(
            f"OCR.space returned no readable text for {file_path} after {_MAX_ATTEMPTS} attempts. "
            "This looks like a temporary service issue rather than an invalid document — please try again."
        )

    parsed = result["ParsedResults"][0]
    raw_text = parsed.get("ParsedText", "")
    confidence = parsed.get("FileParseExitCode", 0)

    # ParseExitCode: 1 = success, others = partial/failed
    avg_confidence = 0.95 if confidence == 1 else 0.7 if confidence == 0 else 0.0

    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

    logger.info(
        "OCR result for %s: lines=%d, raw_text_len=%d, confidence=%.2f, parsed_exit_code=%s",
        file_path,
        len(lines),
        len(raw_text),
        avg_confidence,
        confidence,
    )
    logger.info("OCR raw text for %s: %s", file_path, raw_text[:1000])
    logger.info("OCR parsed lines for %s: %s", file_path, lines)

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


def extract_structured_fields(file_path: str, doc_type: str) -> tuple[dict[str, str], float, str]:
    """Full pipeline: OCR the file, then parse fields for the given document type.

    Returns (fields, confidence, raw_text) where raw_text is the full OCR
    output used for format signature matching.
    """
    if doc_type not in FIELD_PARSERS:
        raise ValueError(f"Unsupported document type: {doc_type}")

    ocr_result = extract_text(file_path)
    fields = FIELD_PARSERS[doc_type](ocr_result)
    raw_text = " ".join(ocr_result.raw_lines)
    return fields, ocr_result.confidence, raw_text