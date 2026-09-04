# ADR-003: SQLite locally, PostgreSQL in production — one codebase

- **Status:** Accepted
- **Date:** 2026-09-04
- **Applies to:** `backend/db.py`, `backend/config.py`, `backend/seed.py`

## Context

A buildathon demo must run anywhere with zero setup (a single SQLite
file), but the live demo on Render needs a shared, durable database
(PostgreSQL) so judges and visitors see one consistent system.

## Decision

The engine is chosen by `DATABASE_URL` alone; every data access goes
through SQLAlchemy ORM so no SQL dialect leaks into business logic.
Local dev defaults to SQLite; Render sets `DATABASE_URL` to Postgres.
Two startup safety nets make the same code safe on both:

1. `init_db()` creates tables idempotently and backfills the `is_test`
   column before any ORM query runs (the seed-before-migrations startup
   ordering bit us in production once — see Session 19).
2. `apply_migrations()` stamps Alembic at head on fresh DBs instead of
   re-running migrations against an ORM-created schema.

## Consequences

- One codebase, two engines — no test-only-vs-prod drift.
- **What changes between engines is exactly where the bugs hide, and
  they were found and fixed during this project:**
  - Postgres rejects `SET boolean_col = 1` (`DatatypeMismatch`) where
    SQLite silently tolerates it — booleans must be bound as real
    booleans (Session 20).
  - SQLite has a single writer (no `SELECT FOR UPDATE` support) — state
    transitions must be safe under serialized writes, which the
    conditional-UPDATE pattern in ADR-008 satisfies on both engines.
  - Postgres persists across deploys; SQLite is per-instance — cleanup
    and archiving logic must work against live shared data (Session 21b).
- Cost: a rare engine-specific SQL construct needs a both-engines test.