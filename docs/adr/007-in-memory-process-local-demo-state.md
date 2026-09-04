# ADR-007: In-memory, process-local state for demo features

- **Status:** Accepted
- **Date:** 2026-09-04
- **Applies to:** `backend/faults.py`, `backend/health.py`

## Context

Two demo-facing features need shared, request-scoped state: the chaos
panel's fault toggles (`faults.py`) and the live system-health metrics
(`health.py`). Options: database tables (persistent, but pollute the DB
and need cleanup), Redis (infrastructure we don't have), or process-local
memory.

## Decision

Both are **in-memory, thread-safe, process-local** registries:

- Fault toggles reset on restart — a demo can never get stuck in an
  outage state, and real outages are never confused with demo ones.
- Health metrics are a sliding window (last hour, capped sample count)
  answering "how is this instance doing right now" — deliberately not a
  historical analytics store.
- Both are safe because Render runs a single web process
  (`WEB_CONCURRENCY=1`), so all requests share the same memory.

## Consequences

- Zero infrastructure, zero DB pollution, zero cleanup scripts.
- A restart clears both — acceptable for both use cases (demo faults
  *should* reset; health is about the live moment).
- The pattern is explicit about its limits: it would break on
  multi-process deployments, which is a documented non-goal for the demo
  (ADR-003).
- Recording is fire-and-forget: a metrics bug can never break a merchant
  upload or verification.