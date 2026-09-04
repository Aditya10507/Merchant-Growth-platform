# Feature brief — Weighted risk score & explainability

> ## ✅ STATUS: IMPLEMENTED — HISTORICAL BUILD BRIEF (do not treat as current)
>
> This feature brief shipped in Sessions 10–14 (see `session_log.md`): `RISK_WEIGHTS`/`MAX_RISK_SCORE` in `config.py`, the nullable `Merchant.risk_score` column, `sort_by_risk` on the merchant list, and the `RiskBadge`/`RiskBreakdown` frontend components — all live in the codebase today.
>
> ⚠️ **Later sessions extended the weights**: `fraud_ring_pan` (40) and `fraud_ring_bank` (40) were added with fraud-ring detection, and `prompt_injection_suspected` (40) with the injection defense. Scoring is centralized in `decision.compute_risk_score` (used by both admin verify and the `risk_eval.py` calibration). Current weights live in `backend/config.py` (`RISK_WEIGHTS`); current architecture in `KNOWLEDGE.md` and `docs/adr/`.
>
> (Note: this file is named `Feature_3.md` but briefs the risk-score feature — an early-session numbering quirk kept for history.)

**Read `KNOWLEDGE.md`, `AGENT_INSTRUCTIONS.md`, and `session_log.md` (all sessions) in full before starting.** This feature builds directly on the Phase 3 admin-verification work already in the repo (`admin.py`'s `verify_application`, `decision.py`'s `check_external_sources`, the `CheckResult`/`VerificationBreakdown` schemas). Do not duplicate that logic — extend it.

---

## 1. What this feature does

Right now, `verify_application` already computes a full list of matched and mismatched checks (`all_matched`, `all_mismatched` in `admin.py`) — but it only uses that list to decide a binary state: `verified_matching` or `verified_mismatched`. This feature adds a **weighted risk score (0–100)** computed from that same data, so the admin panel can:

1. Show a single, glanceable risk number per merchant.
2. **Prioritize** — sort the merchant list by risk score, highest first, so the riskiest applications surface immediately instead of being buried in a flat list.
3. **Explain** — show exactly which checks contributed how many points, so "why is this merchant risky?" has a concrete, visual answer instead of just a pass/fail badge.

This is the single highest-value, lowest-effort addition available, because 100% of the data it needs already exists in `all_matched`/`all_mismatched` — nothing new to compute, only something new to score and display.

---

## 2. Where to work

| File | Change |
|---|---|
| `backend/config.py` | Add `RISK_WEIGHTS: dict[str, int]` — points added to the risk score per mismatched check type. |
| `backend/db.py` | Add `Merchant.risk_score` (Integer, nullable). |
| `backend/schemas.py` | Add `risk_score: Optional[int] = None` to `MerchantSummaryResponse` and `MerchantDetailResponse`. |
| `backend/admin.py` | In `verify_application`, after building `all_mismatched`, compute the risk score and store it. Add a `sort_by_risk` query param to `list_merchants`. |
| `backend/alembic/versions/` | New migration for the `risk_score` column (this repo uses Alembic — see `session_log.md` Session 7/8 for the convention: `alembic revision --autogenerate -m "..."` then review before committing). |
| `frontend/src/types.ts` | Add `risk_score: number \| null` to `MerchantSummary` and `MerchantDetail`. |
| `frontend/src/constants.ts` | Add `RISK_LEVEL_THRESHOLDS` and a `getRiskLevel(score)` helper (or inline in the component — coding agent's call, keep it in constants if used in more than one place). |
| `frontend/src/components/` | New component `RiskBadge.tsx` (colored score pill) and `RiskBreakdown.tsx` (the point-by-point explanation list). |
| `frontend/src/pages/AdminPage.tsx` | Show `RiskBadge` in the merchant list rows and detail header. Add a "Sort by risk" control. Render `RiskBreakdown` in the detail view wherever `mismatched_checks`/`matched_checks` are already shown (see the existing `CheckResultList` usage around lines 542–598). |

---

## 3. Backend implementation

### 3.1 — `config.py`

```python
# Points added to a merchant's risk score for each type of mismatched
# check. Capped at 100 total. Weights reflect how serious each failure
# type is — a government-database mismatch on the PAN itself is worse
# than a missing compliance record, for example.
RISK_WEIGHTS: dict[str, int] = {
    "govt_database": 30,
    "ckyc_records": 20,
    "automated_verification": 20,
    "bank_account_validation": 20,
    "compliance_reviews": 10,
    # LLM cross-check findings are per-field, so each inconsistent field
    # adds a flat amount rather than one fixed weight for "llm_cross_check".
    "llm_cross_check": 15,
}
MAX_RISK_SCORE = 100
```

### 3.2 — `db.py`

```python
# Weighted 0-100 score computed from the verification breakdown at
# verify-time (see admin.py's verify_application). Higher = riskier.
# Null until the admin runs verification.
risk_score = Column(Integer, nullable=True)
```

Run `alembic revision --autogenerate -m "add merchant risk_score"` after this change, review the generated file, then `alembic upgrade head` locally to confirm it applies cleanly.

### 3.3 — `schemas.py`

Add `risk_score: Optional[int] = None` to both `MerchantSummaryResponse` and `MerchantDetailResponse`.

### 3.4 — `admin.py`

Add this function (near the top, alongside `_normalize_checks`):

```python
def _compute_risk_score(mismatched_checks: list[dict]) -> int:
    """
    Weighted sum of mismatched checks, capped at MAX_RISK_SCORE.
    check_name values starting with "llm_cross_check" (e.g.
    "llm_cross_check_name") all map to the flat "llm_cross_check" weight
    — every inconsistent field adds its own points, so multiple LLM
    findings compound, which is intentional (more inconsistencies = more risk).
    """
    from config import settings

    total = 0
    for check in mismatched_checks:
        check_name = check["check_name"]
        weight_key = "llm_cross_check" if check_name.startswith("llm_cross_check") else check_name
        total += settings.RISK_WEIGHTS.get(weight_key, 10)  # unknown check types default to 10
    return min(total, settings.MAX_RISK_SCORE)
```

In `verify_application`, right after this existing block:

```python
    merchant.matched_checks = _json.dumps(all_matched)
    merchant.mismatched_checks = _json.dumps(all_mismatched)
```

add:

```python
    merchant.risk_score = _compute_risk_score(all_mismatched)
```

(A fully matching merchant naturally gets `risk_score = 0`, since `all_mismatched` is empty.)

Update `_merchant_to_summary` to include `risk_score=m.risk_score`, and the `MerchantDetailResponse` construction in `get_merchant_detail` to include `risk_score=merchant.risk_score`.

Update `list_merchants` to accept sorting:

```python
@router.get("/merchants", response_model=list[MerchantSummaryResponse])
def list_merchants(
    status_filter: Optional[str] = None,
    sort_by_risk: bool = False,
    db: Session = Depends(get_db),
    _reviewer: Merchant = Depends(require_role("reviewer", "admin")),
) -> list[MerchantSummaryResponse]:
    query = db.query(Merchant).filter(Merchant.role == "merchant")
    if status_filter:
        query = query.filter(Merchant.onboarding_status == status_filter)
    merchants = query.all()
    if sort_by_risk:
        # None (not yet verified) sorts last, not first — an unscored
        # merchant isn't necessarily low-risk, it just hasn't been checked yet.
        merchants.sort(key=lambda m: (m.risk_score is None, -(m.risk_score or 0)))
    return [_merchant_to_summary(m) for m in merchants]
```

---

## 4. Frontend implementation

### 4.1 — `types.ts`

Add `risk_score: number | null;` to `MerchantSummary` and `MerchantDetail`, mirroring the backend exactly.

### 4.2 — `constants.ts`

```typescript
export const RISK_LEVEL_THRESHOLDS = { LOW: 30, MEDIUM: 60 } as const;

export function getRiskLevel(score: number | null): "unscored" | "low" | "medium" | "high" {
  if (score === null) return "unscored";
  if (score < RISK_LEVEL_THRESHOLDS.LOW) return "low";
  if (score < RISK_LEVEL_THRESHOLDS.MEDIUM) return "medium";
  return "high";
}
```

### 4.3 — `components/RiskBadge.tsx`

```tsx
/**
 * RiskBadge.tsx
 * -------------
 * Colored pill showing a merchant's risk score. Color is never the only
 * signal — the numeric score and a text label are always shown too.
 */
import { memo } from "react";
import { getRiskLevel } from "../constants";

const LEVEL_STYLES: Record<ReturnType<typeof getRiskLevel>, string> = {
  unscored: "bg-gray-100 text-gray-500",
  low: "bg-green-100 text-green-800",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-red-100 text-red-800",
};

const LEVEL_LABELS: Record<ReturnType<typeof getRiskLevel>, string> = {
  unscored: "Not yet scored",
  low: "Low risk",
  medium: "Medium risk",
  high: "High risk",
};

function RiskBadgeBase({ score }: { score: number | null }) {
  const level = getRiskLevel(score);
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium ${LEVEL_STYLES[level]}`}>
      {score !== null && <span className="font-semibold">{score}</span>}
      {LEVEL_LABELS[level]}
    </span>
  );
}

export const RiskBadge = memo(RiskBadgeBase);
```

### 4.4 — `components/RiskBreakdown.tsx`

```tsx
/**
 * RiskBreakdown.tsx
 * -----------------
 * Point-by-point explanation of a merchant's risk score: each mismatched
 * check shown with the points it contributed; matched checks shown as
 * contributing zero. This is the "why this score?" answer for the admin.
 */
import { memo } from "react";
import type { CheckResult } from "../types";

// Mirrors backend/config.py's RISK_WEIGHTS — keep these in sync manually
// (there is no shared-config mechanism between Python and TS here).
const RISK_WEIGHTS: Record<string, number> = {
  govt_database: 30,
  ckyc_records: 20,
  automated_verification: 20,
  bank_account_validation: 20,
  compliance_reviews: 10,
  llm_cross_check: 15,
};

function weightFor(checkName: string): number {
  const key = checkName.startsWith("llm_cross_check") ? "llm_cross_check" : checkName;
  return RISK_WEIGHTS[key] ?? 10;
}

function RiskBreakdownBase({ mismatchedChecks }: { mismatchedChecks: CheckResult[] }) {
  if (mismatchedChecks.length === 0) {
    return <p className="text-sm text-green-700">No risk-contributing checks found.</p>;
  }
  return (
    <ul className="flex flex-col gap-2">
      {mismatchedChecks.map((check, i) => (
        <li key={i} className="flex items-start justify-between gap-3 rounded-md bg-red-50 px-3 py-2 text-sm">
          <span className="text-red-800">{check.detail}</span>
          <span className="shrink-0 font-semibold text-red-900">+{weightFor(check.check_name)}</span>
        </li>
      ))}
    </ul>
  );
}

export const RiskBreakdown = memo(RiskBreakdownBase);
```

### 4.5 — `AdminPage.tsx`

- Import and render `<RiskBadge score={merchant.risk_score} />` next to each merchant row in the list, and in the detail view header.
- Add a "Sort by risk" toggle button that flips a `sortByRisk` boolean and passes `sort_by_risk=true` to `getAdminMerchants` (update `api.ts`'s `getAdminMerchants` signature to accept this param and append it to the query string).
- In the `verified_mismatched` detail section (around the existing `mismatched_checks` rendering), render `<RiskBreakdown mismatchedChecks={detail.mismatched_checks ?? []} />` above or alongside the existing `CheckResultList`.

---

## 5. Coding instructions (same standards as the rest of the project)

- Strict TypeScript, no `any`. Every new function has type hints (Python) / explicit types (TS).
- `RISK_WEIGHTS` exists in two places (`config.py` and `RiskBreakdown.tsx`) because there's no shared-config mechanism between the Python backend and TS frontend in this project — comment both clearly so a future change to one prompts updating the other. Do not try to fetch weights from an API just to avoid duplication; that's over-engineering for a constant that changes rarely.
- `risk_score` is nullable and stays `null` until the admin runs verification — never default it to `0` at merchant creation, since `null` ("not yet assessed") and `0` ("assessed, zero risk found") mean different things and the UI must distinguish them (`RiskBadge`'s `"unscored"` state does this).
- Memoize both new components with `memo()`, matching every other component in `frontend/src/components/`.
- Follow the existing Alembic migration convention documented in `session_log.md` — do not hand-edit `schema.sql` for this; let Alembic generate the migration, then regenerate `schema.sql` for documentation purposes only.

## 6. Phase-wise plan

**Phase 1 — Backend scoring**
- Add `RISK_WEIGHTS`/`MAX_RISK_SCORE` to `config.py`, `risk_score` column + migration to `db.py`.
- Add `_compute_risk_score` and wire it into `verify_application`.
- Test: call `verify_application` (as in previous sessions' `TestClient` pattern) on a merchant with 2 known mismatches (e.g. govt_database + bank_account_validation) and assert `risk_score == 50`. Test a fully clean merchant gets `risk_score == 0`.

**Phase 2 — List sorting**
- Add `sort_by_risk` to `list_merchants`.
- Test: seed 3 merchants with risk scores 10, 80, 40 (directly via DB in the test), call the endpoint with `sort_by_risk=true`, assert order is 80, 40, 10.

**Phase 3 — Frontend**
- Add `RiskBadge`, `RiskBreakdown`, wire into `AdminPage.tsx`.
- Test: `npx tsc -b --noEmit` (zero errors), `npm run build`, then manually verify a mismatched merchant's detail view shows the point breakdown summing to the badge's displayed score.

**Phase 4 — Docs**
- Append a `session_log.md` entry (same convention as prior sessions) describing what changed and why.
