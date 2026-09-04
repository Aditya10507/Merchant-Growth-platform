# ADR-001: The LLM never makes the final decision

- **Status:** Accepted
- **Date:** 2026-09-04
- **Applies to:** `backend/decision.py`, `backend/verify.py`, `backend/admin.py`

## Context

The system uses an LLM for cross-document verification (name on PAN vs GST,
format plausibility). LLMs hallucinate; a hallucinated "all consistent" could
silently approve a fraudulent merchant. The buildathon brief scores
"explain" — every outcome must be traceable to a reason — and an
LLM-only verdict is a black box.

## Decision

The LLM returns **structured findings only** (per-field `consistent`,
`confidence`, `reasoning`) and **never a verdict**. The deterministic
Decision Engine (`decision.py` — rule-based checks against the 5 simulated
external sources + fraud-ring scan + weighted risk score) is the sole
authority on the final outcome. Prompts explicitly forbid approval
recommendations ("You are not authorized to approve or reject the
merchant").

## Consequences

- Outcomes are reproducible and auditable: the same inputs always produce
  the same checks, and each check is explainable.
- An LLM glitch can never cause a false approval — at worst it defers
  verification (see ADR-005).
- The LLM adds value where it is actually reliable: catching *internal
  cross-document inconsistencies* that deterministic format checks can't.
- Cost: the LLM finding is one check among many, not the whole story —
  which is precisely the point.