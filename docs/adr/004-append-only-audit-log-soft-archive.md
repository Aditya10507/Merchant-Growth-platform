# ADR-004: Append-only audit log + soft archiving (never hard delete)

- **Status:** Accepted
- **Date:** 2026-09-04
- **Applies to:** `backend/db.py`, `backend/admin.py`, `backend/documents.py`

## Context

The buildathon track scores "explain": every verification outcome and
admin decision must be reconstructable later. Cleanup needs exist too —
E2E test runs pollute the admin queue and the batch-test accuracy report.
Hard-deleting test data would destroy the audit trail; hard-deleting user
documents would destroy evidence.

## Decision

- **`audit_logs` is append-only.** Every meaningful event — upload,
  verification run, deferral, injection suspicion, manual resolution,
  maintenance action — writes a row with `action`, `reason`, and actor.
  Nothing is ever edited or deleted.
- **Archiving is a soft flag.** Merchants are archived with
  `is_test=True` (excluded from the admin queue and batch-test scoring);
  documents are retired with `is_active=False` (hidden from the
  dashboard, preserved for history). Rows and their audit trails remain.
- Maintenance actions themselves are audit-logged on the actor's own
  trail, so even the cleanup is explainable.

## Consequences

- Full history survives cleanup — the admin can always reconstruct why a
  merchant was verified, deferred, or decided.
- **Lesson learned (Session 21b):** a maintenance cleanup that flags
  merchants lacking ground-truth records accidentally archived a real
  user's account. The design was right (soft flag, reversible), and the
  account was un-archived with its history intact — which is exactly why
  soft archiving beats deletion.
- Cost: storage grows, and queries must consistently filter
  `is_test`/`is_active` — forgetting a filter is the main bug class this
  ADR accepts.