# ADR-007: In-memory, process-local state for demo features

- **Status:** Accepted
- **Date:** 2026-09-04
- **Applies to:** `backend/faults.py`, `backend/health.py`

## Context

Two demo-facing features need shared, request-scoped state: the failure toggles in `faults.py` and the live system-health metrics in `health.py`. The options were database tables (persistent, but pollute the DB and need cleanup), Redis (infrastructure we do not have), or process-local memory.

## Decision

Both are in-memory, thread-safe, process-local registries:

- Failure toggles reset on restart. A demo can never get stuck in an outage state, and real outages are never confused with demo ones.
- Health metrics are a sliding window (last hour, capped sample count) that answers "how is this instance doing right now". They are deliberately not a historical analytics store.
- Both are safe because Render runs a single web process (`WEB_CONCURRENCY=1`), so all requests share the same memory.

## Consequences

- Zero infrastructure, zero database pollution, zero cleanup scripts.
- A restart clears both. That is acceptable for both use cases: demo faults should reset, and health is about the live moment.
- The pattern is explicit about its limits. It would break on multi-process deployments, which is a documented non-goal for the demo (ADR-003).
- Recording is fire-and-forget. A metrics bug can never break a merchant upload or verification.
