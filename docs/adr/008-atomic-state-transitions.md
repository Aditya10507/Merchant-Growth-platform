# ADR-008: Atomic state transitions for admin decisions

- **Status:** Accepted
- **Date:** 2026-09-04
- **Applies to:** `backend/admin.py` (`POST /admin/merchants/{id}/decide`)

## Context

The mandatory human sign-off moves a merchant from `verified_*` to
`active`/`rejected`. Two reviewers can click "Approve" and "Reject" on
the same merchant at the same instant. A naive read-check-write would let
both succeed: two `manual_review_resolution` audit entries, documents
flipped twice, and the last writer silently winning — with no record that
a conflict ever happened.

## Decision

The status transition itself is the serialization point, via a
**conditional UPDATE**:

```sql
UPDATE merchants SET onboarding_status = :new
WHERE id = :id
  AND onboarding_status IN ('verified_matching', 'verified_mismatched')
```

If exactly one row changed, the request proceeds (documents updated,
audit entry written, commit). If **zero** rows changed, the request
rolled back and returns **409** — "already decided by another reviewer."
The WHERE clause is re-evaluated against the committed row, so the second
writer loses the race on both engines: PostgreSQL via row lock + recheck,
SQLite via its single-writer serialization (ADR-003).

## Consequences

- Exactly one decision ever takes effect; exactly one audit entry is
  written. Double-processing is impossible, not just unlikely.
- The losing reviewer gets an explicit, actionable conflict message
  instead of a silent overwrite.
- The pattern is a reusable primitive — the same conditional-UPDATE guard
  applies to any future state machine (e.g. verify-once semantics).
- Cost: the transition is expressed in SQL rather than ORM attribute
  assignment, and the ORM object must be refreshed after the core UPDATE
  (documented in code).