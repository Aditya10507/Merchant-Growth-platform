# ADR-001: The LLM never makes the final decision

- **Status:** Accepted
- **Date:** 2026-09-04
- **Applies to:** `backend/decision.py`, `backend/verify.py`, `backend/admin.py`

## Context

The system uses an LLM for cross-document verification (name on PAN vs GST, format plausibility). LLMs can hallucinate. A hallucinated "all consistent" result could silently approve a fraudulent merchant. The buildathon brief also scores "explain": every outcome must be traceable to a reason, and an LLM-only verdict is a black box.

## Decision

The LLM returns structured findings only (per-field `consistent`, `confidence`, `reasoning`) and never a verdict. The deterministic Decision Engine in `decision.py` (rule-based checks against the 5 simulated external sources, a fraud-ring scan, and a weighted risk score) is the sole authority on the final outcome. The prompts explicitly forbid approval recommendations: "You are not authorized to approve or reject the merchant."

## Consequences

- Outcomes are reproducible and auditable. The same inputs always produce the same checks, and each check is explainable.
- An LLM glitch can never cause a false approval. At worst it defers verification (see ADR-005).
- The LLM adds value where it is actually reliable: catching internal cross-document inconsistencies that deterministic format checks cannot.
- Cost: the LLM finding is one check among many, not the whole story. That is precisely the point.
