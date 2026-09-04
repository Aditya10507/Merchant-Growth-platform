"""
verify.py
---------
Calls an LLM API (Groq / OpenAI-compatible) to cross-verify extracted
document fields.

Design principle (critical to the whole system's safety):
    The LLM NEVER makes the final approve/reject decision. It only
    returns structured findings (per-field consistency, confidence,
    reasoning). The deterministic Decision Engine (decision.py) is the
    sole authority on the final outcome. This keeps the system
    auditable and immune to LLM hallucination causing a false approval.

The prompt is deliberately strict:
    - Forces JSON-only output (parsed and validated against a schema).
    - Explicitly forbids guessing missing data.
    - Requires a confidence score and reasoning per field.
"""

import json
import logging

from openai import OpenAI, APIError

from config import settings
from schemas import LlmVerificationResult

logger = logging.getLogger(__name__)
_client: OpenAI | None = None


class LlmVerificationError(RuntimeError):
    """Raised when the LLM call fails or returns an unparseable response."""


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
    return _client


_SYSTEM_PROMPT = """You are a document verification assistant for a fintech \
merchant onboarding system. You will be given extracted fields from \
multiple KYC documents belonging to the same merchant.

Your ONLY job is to check internal consistency between the documents \
(e.g. does the name on the PAN card match the name on the GST \
certificate; are formats plausible for the document type).

STRICT RULES — you must follow all of them:
1. Respond with ONLY a single valid JSON object. No prose, no markdown \
   fences, no explanation outside the JSON.
2. Never invent, assume, or fill in a value that was not provided in the \
   input. If a field is missing or empty, mark it as inconsistent with \
   reasoning "field missing from extracted data" — do not guess.
3. Every finding must include a confidence score between 0.0 and 1.0 \
   reflecting how certain you are, and a short factual reasoning string.
4. You are not authorized to approve or reject the merchant. You only \
   report findings. Do not include any approval recommendation.
5. If you are uncertain whether two values match (e.g. minor spelling \
   variation), mark consistent=false with confidence reflecting your \
   uncertainty rather than assuming they match.

Respond with JSON matching exactly this shape:
{
  "overall_consistent": boolean,
  "findings": [
    {"field_name": string, "consistent": boolean, "confidence": number, "reasoning": string}
  ],
  "summary": string
}
"""


def cross_verify_documents(documents_fields: dict[str, dict[str, str]]) -> LlmVerificationResult:
    """
    documents_fields: e.g. {"PAN": {"name": "...", "pan_number": "..."},
                             "GST": {"name": "...", "gst_number": "..."}}

    Demo fault hook: when the llm_down fault is active (admin chaos
    panel), this raises LlmVerificationError exactly like a real LLM
    outage would — admin.py then defers verification instead of making
    a determination on partial signals.

    Metrics: every outcome (success or failure) is recorded to health.py
    so the admin system-health view can report LLM success rate and
    latency. Recording never raises — a metrics bug cannot break verify.
    """
    import time

    import health

    start = time.monotonic()
    try:
        result = _cross_verify_impl(documents_fields)
    except Exception:
        health.record_llm(ok=False, latency_ms=(time.monotonic() - start) * 1000)
        raise
    health.record_llm(ok=True, latency_ms=(time.monotonic() - start) * 1000)
    return result


def _cross_verify_impl(documents_fields: dict[str, dict[str, str]]) -> LlmVerificationResult:
    """Internal implementation of cross_verify_documents (see wrapper
    above for the metrics + docstring; this holds the actual call).
    """
    import faults
    if faults.is_active("llm_down"):
        raise LlmVerificationError(
            "Simulated LLM outage (demo fault: llm_down). No determination will "
            "be made until the service recovers."
        )

    user_content = json.dumps(documents_fields, ensure_ascii=False)

    try:
        response = _get_client().chat.completions.create(
            model=settings.LLM_MODEL,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
    except APIError as exc:
        raise LlmVerificationError(f"LLM API call failed: {exc}") from exc

    raw_text = (response.choices[0].message.content or "").strip()

    try:
        parsed = json.loads(raw_text)
        return LlmVerificationResult.model_validate(parsed)
    except (json.JSONDecodeError, ValueError) as exc:
        # A malformed response is treated as a hard failure, never as a
        # silent "assume consistent" — see decision.py, which routes
        # this exception to a manual-review outcome.
        raise LlmVerificationError(
            f"LLM returned a response that did not match the expected schema: {raw_text[:200]}"
        ) from exc


# ---------------------------------------------------------------------------
# Humanize technical reasons for merchant-facing display
# ---------------------------------------------------------------------------

_HUMANIZE_SYSTEM_PROMPT = """You rephrase an internal verification system's \
technical rejection/flag reason into one or two short, plain-language \
sentences for a small business owner with no technical background.

STRICT RULES:
1. Only rephrase what is given. Never add a fact, number, or explanation \
   that isn't already present in the input.
2. Never mention internal system details: no OCR, no "LLM", no AI model \
   names, no database/table names, no confidence scores as raw numbers.
3. If the input implies a corrective action (e.g. re-upload a clearer \
   image), state that action plainly. If it doesn't, don't invent one.
4. Respond with ONLY the rephrased message. No preamble, no quotes, no \
   markdown.
"""


def humanize_reason(technical_reason: str) -> str:
    """
    Converts a technical rejection/flag reason into plain-language text
    suitable for display to the merchant. This function only rephrases
    — it never generates a new reason or implies an approval/rejection
    decision.

    On any LLM failure, falls back to the original technical reason
    rather than crashing or leaving the merchant with nothing.
    """
    try:
        response = _get_client().chat.completions.create(
            model=settings.LLM_MODEL,
            max_tokens=200,
            messages=[
                {"role": "system", "content": _HUMANIZE_SYSTEM_PROMPT},
                {"role": "user", "content": technical_reason},
            ],
        )
        raw_text = (response.choices[0].message.content or "").strip()
        return raw_text or technical_reason
    except Exception:
        # Humanizing is a nice-to-have, never a blocker. On any failure,
        # fall back to the original technical reason rather than
        # crashing the request or leaving the merchant with nothing.
        logger.warning("humanize_reason failed, falling back to technical reason", exc_info=True)
        return technical_reason


# ---------------------------------------------------------------------------
# Generate a rejection cause from structured mismatched checks
# ---------------------------------------------------------------------------

_REJECTION_CAUSE_PROMPT = """You are writing a plain-language explanation for a small business \
owner whose identity verification had multiple issues.

You will be given a list of mismatched checks, each with a check name, \
the document it relates to, and a technical detail.

STRICT RULES:
1. Write one to three short, clear sentences that mention which documents \
   had issues and what the problems were — in plain language, no jargon.
2. Do NOT mention internal system names (no "govt_database", no \
   "ckyc_records", no table names, no "LLM", no "OCR", no confidence \
   scores as raw numbers).
3. If multiple documents are affected, mention each one clearly so the \
   merchant knows exactly what to fix.
4. If the checks imply a corrective action (e.g. re-upload a clearer \
   image, check your bank details), state that plainly.
5. Respond with ONLY the explanation. No preamble, no quotes, no markdown.
"""


def generate_rejection_cause(mismatched_checks: list[dict[str, str]]) -> str:
    """
    Turns a list of mismatched CheckResult dicts into one clear,
    merchant-facing explanation.

    This follows the same anti-hallucination rules as humanize_reason():
    it only rephrases what's in the input, never invents new information,
    never mentions internal system names.

    If the LLM call fails, falls back to a plain-text join of the
    mismatched details so the merchant always gets *something*.
    """
    if not mismatched_checks:
        return ""

    # Build a structured summary of each mismatch for the LLM
    summary_lines = []
    for check in mismatched_checks:
        summary_lines.append(
            f"- Document '{check.get('document_type', 'unknown')}': "
            f"{check.get('detail', 'check failed')}"
        )
    user_content = "\n".join(summary_lines)

    try:
        response = _get_client().chat.completions.create(
            model=settings.LLM_MODEL,
            max_tokens=250,
            messages=[
                {"role": "system", "content": _REJECTION_CAUSE_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        raw_text = (response.choices[0].message.content or "").strip()
        return raw_text or _fallback_cause(mismatched_checks)
    except Exception:
        logger.warning("generate_rejection_cause failed, using fallback", exc_info=True)
        return _fallback_cause(mismatched_checks)


_DOC_TYPE_NAMES: dict[str, str] = {
    "PAN": "PAN card",
    "GST": "GST certificate",
    "BANK_PROOF": "bank proof document",
}


def _fallback_cause(mismatched_checks: list[dict[str, str]]) -> str:
    """User-friendly fallback when the LLM call fails.

    Groups mismatches by document type and produces one short sentence
    per affected document, e.g.:
      "Your PAN card could not be verified against government records.
       Your bank proof document was not found in our validation system."
    """
    from collections import defaultdict

    by_doc: dict[str, list[str]] = defaultdict(list)
    for check in mismatched_checks:
        doc = check.get("document_type", "document")
        detail = check.get("detail", "verification failed")
        by_doc[doc].append(detail)

    parts: list[str] = []
    for doc_type, details in by_doc.items():
        friendly_name = _DOC_TYPE_NAMES.get(doc_type, doc_type.replace("_", " ").lower())
        # Pick the most meaningful detail — prefer "not found" over raw
        # internal messages, and drop fraud-ring details (those are
        # admin-facing, not merchant-facing).
        merchant_details = [
            d for d in details
            if "appears on merchant" not in d
        ]
        if not merchant_details:
            continue
        # Summarise: if the first detail says "not found", say it plainly
        first = merchant_details[0]
        if "not found" in first.lower() or "no " in first.lower():
            parts.append(f"Your {friendly_name} could not be verified.")
        elif "failed" in first.lower() or "invalid" in first.lower() or "flagged" in first.lower():
            parts.append(f"Your {friendly_name} did not pass verification.")
        else:
            parts.append(f"Your {friendly_name} could not be verified.")

    if not parts:
        return "Your application could not be verified. Please check your documents and try again."

    return " ".join(parts) + " Please review your documents and reapply."
