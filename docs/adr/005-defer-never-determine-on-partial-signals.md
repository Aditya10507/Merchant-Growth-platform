# ADR-005: Defer verification, never determine on partial signals

- **Status:** Accepted
- **Date:** 2026-09-04
- **Applies to:** `backend/admin.py`, `backend/decision.py`, `backend/verify.py`

## Context

Verification combines an LLM cross-document check, 5 external sources, and a fraud-ring scan. Any of these can be unavailable (a real outage, or the demo's `llm_down` and `sources_down` toggles). An earlier version caught an LLM error and continued with external checks only. That could silently approve a merchant whose cross-document inconsistency only the LLM could catch.

## Decision

The LLM and the external sources are required signals. If either is unavailable:

- Verification defers: HTTP 503, the merchant stays in `submitted`, and a `verification_deferred` audit entry records the reason.
- No determination is made on partial signals. Scoring a merchant against silence is a false confidence we refuse to produce.

OCR extraction failures are handled differently by design. They are merchant-facing and retry-friendly (`temporarily_unavailable`), never a hard rejection (see ADR-002).

## Consequences

- A broken dependency can never turn into a wrong approve or reject. The system fails safe.
- The demo story is strong: toggle `llm_down`, watch verify defer with an explainable audit entry, clear it, and watch the same merchant verify cleanly.
- Cost: an outage pauses verification until recovery. That is correct behavior for a risk system, and the merchant-visible messaging makes clear this is a retry, not a rejection.
