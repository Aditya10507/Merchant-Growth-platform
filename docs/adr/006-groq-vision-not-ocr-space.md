# ADR-006: Groq vision (qwen) as the extraction engine instead of OCR.space

- **Status:** Accepted (supersedes the original OCR.space choice)
- **Date:** 2026-09-04
- **Applies to:** `backend/ocr.py`

## Context

The original extraction engine (OCR.space free tier) intermittently
returned empty/garbled results for perfectly valid documents — including
failing the same PAN and GST images live that it had extracted cleanly
before (Sessions 16–18). Retries mitigated but never fixed it. False
negatives on valid documents are the worst failure mode for an onboarding
system: real merchants get rejected by noise.

## Decision

Swap the engine to the project's **existing Groq vision model**
(`qwen/qwen3.8-27b`) behind the same `extract_structured_fields()`
interface, so no calling code changed (dependency inversion in `ocr.py`
made the swap a one-module change). The vision model returns typed JSON
fields per document type in one call — replacing the old two-step
text-OCR + regex parsing that produced the false results. The swap cost
zero new signups: the Groq key and OpenAI-compatible client already
existed for LLM verification.

## Consequences

- Extraction accuracy improved on exactly the documents the old engine
  garbled; the live E2E suite extracted every identifier exactly.
- No new credential surface — one provider (Groq) powers both extraction
  and verification.
- **New constraint:** Groq's free tier has a daily token quota shared by
  both features; heavy testing can exhaust it, surfacing as retry-friendly
  `temporarily_unavailable`. Mitigation is documented: `LLM_FALLBACK_KEYS`
  from *other* Groq accounts (per-account limits), plus the existing
  retry/backoff paths.
- Lesson retained: the `ocr.py` interface abstraction is what made this
  swap cheap — and makes the next one cheap too.