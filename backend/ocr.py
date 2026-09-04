"""
ocr.py
------
Wraps Groq vision (the project's LLM API) as the document-extraction
engine so the rest of the app never touches the OCR/vision provider
directly (Dependency Inversion — callers depend on this module's small
interface, not on the Groq API). This made it possible to swap the OCR
engine from OCR.space to Groq vision without touching any calling code.

extract_structured_fields() sends the document image to a Groq vision
model (qwen/qwen3.6-27b or qwen/qwen3.8-27b — the only vision-capable
models on Groq) and asks it to return the typed fields for the document
type directly as JSON. This replaces the old two-step flow (OCR.space
text extraction + fragile regex field parsing): the vision model reads
the document and returns `pan_number`, `name`, `dob`, etc. in one call,
which eliminates the regex/name-guessing heuristics that produced false
extraction results on noisy synthetic documents.

Setup:
  1. Use the project's existing Groq key (LLM_API_KEY in backend/.env)
     — no separate OCR signup required.
  2. LLM_MODEL must be a Groq vision-capable model. The default
     (qwen/qwen3.8-27b) is one. gpt-oss-120b/20b are TEXT-ONLY on Groq
     and will not work for extraction (Groq rejects image input for
     them with "content must be a string").

--- Why vision instead of OCR.space (Session 20) ---
OCR.space's free tier intermittently returned empty/garbled results for
perfectly valid documents (Sessions 16-18: UJALK5542W and HAOEL7625O
both failed live runs while extracting cleanly in others). Retries
mitigated but never fixed it. Benchmarking the project's own Groq model
(qwen/qwen3.8-27b) against the same failing documents extracted every
identifier correctly (PAN, GST, IFSC, account) on the first pass —
including the two documents OCR.space routinely garbled. Since the
project already has a working Groq key and OpenAI-compatible client,
swapping the engine cost zero new signups or credentials.

Reliability semantics preserved from the OCR.space era:
  - Retries with exponential backoff on transient failures (rate limit,
    network, 5xx) before giving up.
  - OcrTemporarilyUnavailableError — raised only for genuine service
    hiccups after retries are exhausted, so callers can show the
    merchant "try again in a moment" instead of a hard rejection.
  - OcrEngineError — configuration/usage errors that retrying cannot
    fix (invalid key, model blocked, unsupported file), so a broken
    setup surfaces loudly rather than pretending the document is bad.

--- Multi-key failover ---
Groq rate limits apply at the account/organization level, not per key,
so multiple keys on ONE account add no capacity. If LLM_FALLBACK_KEYS
(comma-separated) contains keys from OTHER Groq accounts, extraction
automatically rotates to the next key on 401/403/429 errors so a hit
rate limit on one account falls through to another. With a single key
this is a no-op.
"""

import base64
import io
import json
import logging
import re
import threading
import time

from openai import OpenAI

from config import settings

logger = logging.getLogger(__name__)


class OcrEngineError(RuntimeError):
    """Raised when document extraction fails for a reason that retrying
    cannot fix — invalid/missing API key, model blocked for the account,
    unsupported file content. These are configuration or usage errors,
    not transient service hiccups."""


class OcrTemporarilyUnavailableError(OcrEngineError):
    """Raised when the extraction service did not cooperate after all
    retry attempts (rate limit exhausted across every configured key,
    repeated network/5xx failures). Deliberately a DIFFERENT exception
    from OcrEngineError's config cases: it means "the service didn't
    cooperate right now", not "this document is invalid." Callers show
    the merchant a retry-friendly message."""


# Vision-capable models on Groq (per Groq docs, only these accept images).
_VISION_MODELS = ("qwen/qwen3.6-27b", "qwen/qwen3.8-27b")

# Groq free-tier pacing: ~30 req/min but each image costs ~2048 tokens
# against a ~8K token/min budget, so back-to-back image calls must be
# spaced out. Documents are uploaded one at a time by a human, so a
# 2s minimum interval is plenty; E2E batch runs rely on the 429
# retry/backoff below when a minute budget is hit.
_MIN_CALL_INTERVAL_SECONDS = 2.0

_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = [2.0, 4.0, 8.0]  # delay before attempts 2, 3

_RATE_LIMITER_LOCK = threading.Lock()
_last_call_time: float = 0.0


def _pace_calls() -> None:
    """Sleeps if needed so consecutive API calls respect the pacing interval."""
    global _last_call_time
    with _RATE_LIMITER_LOCK:
        elapsed = time.time() - _last_call_time
        if elapsed < _MIN_CALL_INTERVAL_SECONDS:
            time.sleep(_MIN_CALL_INTERVAL_SECONDS - elapsed)
        _last_call_time = time.time()


def _get_api_keys() -> list[str]:
    """Primary key first, then any fallback keys from other accounts."""
    keys = [settings.LLM_API_KEY]
    for k in settings.LLM_FALLBACK_KEYS:
        k = k.strip()
        if k and k not in keys:
            keys.append(k)
    if not keys or not keys[0]:
        raise OcrEngineError(
            "LLM_API_KEY is not set. Get a free Groq key at https://console.groq.com "
            "and add it as an environment variable: LLM_API_KEY=your_key_here"
        )
    return keys


# ---------------------------------------------------------------------------
# Image preparation (incl. PDF rasterization)
# ---------------------------------------------------------------------------

_MIME_BY_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"%PDF", "application/pdf"),
)


def _image_data_url(file_content: bytes) -> str:
    """Returns a base64 data URL for the vision call.

    PNG/JPEG are passed through directly. PDFs are rasterized (first
    page rendered to PNG via pypdfium2) because Groq vision accepts
    images only, not PDF bytes — this preserves the project's existing
    "JPG, PNG, or PDF" upload contract.
    """
    mime = None
    for magic, candidate in _MIME_BY_MAGIC:
        if file_content[: len(magic)] == magic:
            mime = candidate
            break
    if mime is None:
        raise OcrEngineError(
            "Unsupported file content. Upload a PNG, JPEG, or PDF document image."
        )

    if mime == "application/pdf":
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:
            raise OcrEngineError(
                "PDF support requires pypdfium2 (pip install pypdfium2)."
            ) from exc
        try:
            doc = pdfium.PdfDocument(io.BytesIO(file_content))
            page = doc[0]  # first page only — KYC documents are single-page
            bitmap = page.render(scale=2.0)
            pil_image = bitmap.to_pil()
            doc.close()
        except Exception as exc:
            raise OcrEngineError(f"Could not read the uploaded PDF: {exc}") from exc
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
        mime = "image/png"
    else:
        image_bytes = file_content

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _image_is_blank(file_content: bytes) -> bool:
    """True for images too small to contain readable text (e.g. a 1x1
    fake PNG). Groq vision rejects these up front with a 400, which we
    must NOT surface as a hard document rejection — a blank image is a
    merchant mistake, handled as invalid_format by the caller. Reads
    only the image header (lazy decode), never the full pixel data."""
    try:
        from PIL import Image
        from PIL import UnidentifiedImageError
    except ImportError:
        return False  # PIL missing — let the API call decide
    try:
        with Image.open(io.BytesIO(file_content)) as img:
            return img.width < 2 or img.height < 2
    except (UnidentifiedImageError, OSError):
        # Can't be parsed as an image at all — not "blank but valid";
        # the caller's format handling / API call will surface it.
        return False


# ---------------------------------------------------------------------------
# Vision extraction
# ---------------------------------------------------------------------------

# Per-document-type extraction schemas. Keys match what documents.py and
# verify.py expect (pan_number, gst_number, ifsc, account_number, name, dob).
_DOC_TYPE_SCHEMAS: dict[str, dict[str, str]] = {
    "PAN": {
        "pan_number": "the 10-character PAN number (e.g. ABCDE1234F)",
        "name": "the full name printed on the card",
        "dob": "the date of birth in DD/MM/YYYY format if visible",
    },
    "GST": {
        "gst_number": "the 15-character GSTIN (e.g. 27ABCDE1234F1Z5)",
        "name": "the legal/business name printed on the certificate",
    },
    "BANK_PROOF": {
        "ifsc": "the 11-character IFSC code (e.g. HDFC0001234)",
        "account_number": "the bank account number",
        "name": "the account holder name printed on the document",
    },
}

_SYSTEM_PROMPT = """You are a document extraction engine for Indian KYC \
documents in a merchant onboarding system. You receive an image of ONE \
document and must return ONLY a single valid JSON object with the exact \
fields requested — no prose, no markdown fences, no explanation.

STRICT RULES:
1. Read every visible value carefully from the image. NEVER invent, \
guess, or auto-correct a value that is not visibly printed. If a field \
is not visible, return an empty string "" for it.
2. Do not "fix" OCR-style noise — transcribe exactly what you see.
3. Return only JSON that matches the requested keys exactly."""


def _build_prompt(doc_type: str) -> str:
    schema = _DOC_TYPE_SCHEMAS[doc_type]
    lines = [f"Extract these fields from the {doc_type.replace('_', ' ')} document:"]
    for key, desc in schema.items():
        lines.append(f'- "{key}": {desc}')
    lines.append('Respond with ONLY: {"' + '": "...", "'.join(schema.keys()) + '": "..."}')
    return "\n".join(lines)


def _parse_json_response(raw: str) -> dict:
    """Parses the model's response into a dict, tolerating think blocks
    and markdown fences around the JSON."""
    raw = (raw or "").strip()
    # qwen vision models may emit a <think> block before the JSON.
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # Strip ```json ... ``` fences if present.
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Last resort: grab the first {...} chunk.
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        # A malformed response is a transient model glitch worth retrying,
        # not a config error — ValueError is caught by the retry loop below.
        raise ValueError(
            f"Vision model returned a response that was not valid JSON: {raw[:200]}"
        )


def _normalize_fields(parsed: dict, doc_type: str) -> dict[str, str]:
    """Keeps only the fields this document type expects, coerced to str
    (missing/None → ""), so downstream code never sees surprises."""
    fields: dict[str, str] = {}
    for key in _DOC_TYPE_SCHEMAS[doc_type]:
        value = parsed.get(key)
        fields[key] = str(value).strip() if value is not None else ""
    return fields


def _call_vision_once(file_path: str, file_content: bytes, doc_type: str, api_key: str) -> dict:
    """One extraction attempt with one API key. Returns normalized fields.

    Raises OcrEngineError for configuration errors (bad key, blocked
    model, unsupported request) and returns normally on success. Rate
    limit / 5xx / network errors are surfaced to the caller via the
    exception type so the retry loop can rotate keys and back off.
    """
    data_url = _image_data_url(file_content)

    # Sanity check: only vision-capable models can extract from images.
    if settings.LLM_MODEL not in _VISION_MODELS:
        logger.warning(
            "LLM_MODEL=%s is not a Groq vision model (%s) — image extraction "
            "will fail. qwen/qwen3.8-27b is the recommended model.",
            settings.LLM_MODEL, ", ".join(_VISION_MODELS),
        )

    client = OpenAI(api_key=api_key, base_url=settings.LLM_BASE_URL)
    try:
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            max_tokens=600,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _build_prompt(doc_type)},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
    except Exception as exc:  # openai raises typed exceptions; classify below
        logger.warning("Vision call failed for %s: %s: %s", file_path, type(exc).__name__, exc)
        from openai import BadRequestError

        if isinstance(exc, BadRequestError):
            # Malformed request (e.g. image too large, model cannot take
            # images) — deterministic, not worth retrying.
            raise OcrEngineError(f"Vision request rejected: {exc}") from exc
        # Everything else (AuthenticationError, PermissionDeniedError,
        # RateLimitError, APIConnectionError, InternalServerError, timeouts)
        # propagates so the retry loop can rotate keys and back off.
        raise

    raw_content = (response.choices[0].message.content or "").strip()
    if not raw_content:
        raise ValueError("Vision model returned an empty response.")
    parsed = _parse_json_response(raw_content)
    return _normalize_fields(parsed, doc_type)


def extract_structured_fields(file_path: str, doc_type: str) -> tuple[dict[str, str], float, str]:
    """Full pipeline: send the document image to the Groq vision model
    and get typed fields back.

    Returns (fields, confidence, raw_text) where:
      - fields is a dict with exactly the expected keys for doc_type
        (empty string for any field the model could not see)
      - confidence approximates how complete the extraction was
        (informational — the deterministic checks are authoritative)
      - raw_text is the extracted values joined, used by documents.py's
        format-signature check (mirrors the old OCR-text interface)

    Raises OcrTemporarilyUnavailableError if every key/attempt failed on
    transient errors (rate limit, network, 5xx), and OcrEngineError for
    configuration/usage errors retrying cannot fix.

    Metrics: every outcome (success or failure) is recorded to health.py
    so the admin system-health view can report OCR success rate and
    latency. Recording never raises — a metrics bug cannot break uploads.
    """
    import health

    start = time.monotonic()
    try:
        result = _extract_structured_fields_impl(file_path, doc_type)
    except Exception:
        health.record_ocr(ok=False, latency_ms=(time.monotonic() - start) * 1000)
        raise
    health.record_ocr(ok=True, latency_ms=(time.monotonic() - start) * 1000)
    return result


def _extract_structured_fields_impl(file_path: str, doc_type: str) -> tuple[dict[str, str], float, str]:
    """Internal implementation of extract_structured_fields (see wrapper
    above for the metrics + docstring; this holds the actual pipeline).
    """
    if doc_type not in _DOC_TYPE_SCHEMAS:
        raise OcrEngineError(f"Unsupported document type: {doc_type}")

    # Demo fault hook (admin chaos panel): simulate an OCR outage. Raises
    # the retry-friendly exception so uploads surface exactly the same
    # "temporarily_unavailable" status a real outage produces — and
    # recover instantly when the fault is cleared.
    import faults
    if faults.is_active("ocr_down"):
        raise OcrTemporarilyUnavailableError(
            "Simulated OCR outage (demo fault: ocr_down). Please try again shortly."
        )

    try:
        with open(file_path, "rb") as f:
            file_content = f.read()
    except FileNotFoundError:
        raise OcrEngineError(f"File not found: {file_path}")
    except Exception as exc:
        raise OcrEngineError(f"Failed to read file {file_path}: {exc}") from exc

    api_keys = _get_api_keys()

    # Validate the file up front so a genuinely unsupported/broken file
    # raises OcrEngineError (not a retry-able service error).
    _image_data_url(file_content)  # raises OcrEngineError if unreadable

    # A blank image (e.g. the classic 1x1 fake PNG) is a merchant
    # mistake, NOT a document worth rejecting with a hard status. Return
    # empty fields so documents.py's "no readable text" path marks it
    # invalid_format (retry in the same slot) without ever calling the
    # API (which would 400 with a raw technical message).
    if _image_is_blank(file_content):
        logger.info("%s is a blank/undersized image — returning empty fields", file_path)
        empty_fields = {key: "" for key in _DOC_TYPE_SCHEMAS[doc_type]}
        return _finalize(empty_fields, doc_type)

    transient_failures: list[str] = []
    all_empty_attempts = 0

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        for key_index, api_key in enumerate(api_keys):
            _pace_calls()
            try:
                fields = _call_vision_once(file_path, file_content, doc_type, api_key)
                if not any(fields.values()):
                    # The model read the image but found no fields at all.
                    # For a genuinely blank file this is caught earlier;
                    # reaching here means the model glitched or the image
                    # truly has no readable content — mirror the old
                    # OCR.space empty-result retry behavior before giving up.
                    all_empty_attempts += 1
                    logger.warning(
                        "Vision extraction returned empty fields for %s (%s) "
                        "attempt %d/%d — retrying (all_empty_attempts=%d)",
                        file_path, doc_type, attempt, _MAX_ATTEMPTS, all_empty_attempts,
                    )
                    transient_failures.append("model returned empty fields")
                    if all_empty_attempts >= _MAX_ATTEMPTS:
                        # Exhausted retries: report as empty (not an error) so
                        # documents.py shows "no readable text" (invalid_format)
                        # rather than a hard rejection or a false "unavailable".
                        logger.error(
                            "Vision extraction returned empty fields for %s (%s) "
                            "on all %d attempts",
                            file_path, doc_type, _MAX_ATTEMPTS,
                        )
                        empty_fields = {key: "" for key in _DOC_TYPE_SCHEMAS[doc_type]}
                        return _finalize(empty_fields, doc_type)
                    continue
                logger.info(
                    "Vision extraction succeeded for %s (%s): fields=%s",
                    file_path, doc_type, fields,
                )
                return _finalize(fields, doc_type)
            except OcrEngineError:
                raise  # config/usage error — do not retry
            except Exception as exc:  # auth/permission/rate/network — rotate or retry
                logger.warning(
                    "Vision attempt %d key %d/%d failed for %s: %s: %s",
                    attempt, key_index + 1, len(api_keys), file_path, type(exc).__name__, exc,
                )
                transient_failures.append(f"{type(exc).__name__}: {exc}")
                # Try the next key on the same attempt — but if every key
                # just failed with auth/permission, retrying is pointless.
                from openai import (
                    APIConnectionError,
                    AuthenticationError,
                    InternalServerError,
                    PermissionDeniedError,
                    RateLimitError,
                )

                if isinstance(exc, (AuthenticationError, PermissionDeniedError)) and key_index == len(api_keys) - 1:
                    # All keys rejected the request on auth/permissions.
                    raise OcrEngineError(
                        f"Vision API key rejected ({type(exc).__name__}). "
                        "Check LLM_API_KEY and that the model is enabled in "
                        "project settings at console.groq.com/settings/project/limits."
                    ) from exc
                continue

        if attempt < _MAX_ATTEMPTS:
            backoff = _RETRY_BACKOFF_SECONDS[attempt - 1]
            logger.warning(
                "All %d key(s) failed on attempt %d/%d for %s — backing off %.0fs",
                len(api_keys), attempt, _MAX_ATTEMPTS, file_path, backoff,
            )
            time.sleep(backoff)

    # Every key and attempt exhausted on transient errors → service hiccup.
    detail = "; ".join(transient_failures[-3:]) or "unknown"
    raise OcrTemporarilyUnavailableError(
        f"Document extraction service is temporarily unavailable after "
        f"{_MAX_ATTEMPTS} attempts ({detail}). Please try again in a moment."
    )


def _finalize(fields: dict[str, str], doc_type: str) -> tuple[dict[str, str], float, str]:
    """Derives confidence + raw_text from the extracted fields.

    Confidence is informational only (the deterministic Decision Engine
    is authoritative): 0.95 when the document-type identifier was found,
    0.7 when only secondary fields were found, 0.0 when nothing at all.
    """
    present = [v for v in fields.values() if v]
    raw_text = " ".join(present)

    primary_keys = {
        "PAN": ["pan_number"],
        "GST": ["gst_number"],
        "BANK_PROOF": ["ifsc", "account_number"],
    }[doc_type]
    if any(fields.get(k) for k in primary_keys):
        confidence = 0.95
    elif present:
        confidence = 0.7
    else:
        confidence = 0.0

    return fields, confidence, raw_text
