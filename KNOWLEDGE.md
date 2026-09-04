# KNOWLEDGE.md

This file exists so an AI coding agent (or a human joining later) can understand this project's context, decisions, and constraints without re-reading every file. Read this before making changes.

## What this project is

**Merchant Onboarding Copilot** — built for the Razorpay AI Buildathon 2026 ("AI Risk Manager" track). A merchant signs up and uploads PAN, GST, and bank-proof documents. The system extracts typed fields (Groq vision), runs a deterministic verification pipeline (LLM cross-document consistency + 5 simulated external data sources + cross-merchant fraud-ring scan), computes a weighted **risk score (0–100)**, and presents the full structured breakdown to a **human admin who makes the mandatory final approve/reject decision**. Nothing ever activates a merchant without an explicit admin sign-off — a deliberate human-in-the-loop compliance design.

The buildathon brief is "identify, assess, prioritize, or explain risk" — every feature maps to that: mismatch/fraud detection (identify), risk score (assess), risk-sorted queue (prioritize), audit trail + per-check breakdown (explain). Growth/marketing/payments features are off-track; reliability, explainability, and audit-trail work is always on-track.

Full design context:
- `docs/adr/` — **Architecture Decision Records (8)** — the "why" behind the key design calls (LLM never decides, sync OCR over queues, SQLite→Postgres, defer-on-partial-signals, vision-OCR swap, atomic decisions, …). Read these before changing a core design.
- `docs/01_PRD.md`, `docs/02_Architecture.md`, `docs/03_UIUX.md` — product, architecture/SRS, UI/UX (kept current).
- `session_log.md` — chronological record of every session and the source of truth when anything conflicts.

## Non-negotiable design decisions — do not casually change these

1. **The LLM never makes the final approve/reject decision — and verification is admin-triggered, never automatic.** `verify.py` calls Groq and returns structured *findings* only. `decision.py` is the deterministic authority. `verify_application()` (admin clicking "Verify with internal databases", `POST /admin/merchants/{id}/verify`) runs the LLM cross-check + all 5 external sources + fraud-ring scan on demand and stores a structured `matched_checks`/`mismatched_checks` breakdown. The only code path that sets `onboarding_status` to `"active"` or `"rejected"` is `decide_application()` (`POST /admin/merchants/{id}/decide`) — an explicit admin action. If you're tempted to have any automated path set a merchant's status directly, don't.

2. **A merchant's status machine is:** `pending` → `submitted` (all 3 docs format-valid → no auto-verification) → admin triggers verify → `verified_matching` (all checks passed → one-click approve) **or** `verified_mismatched` (mismatches found → admin reviews the breakdown, may edit the auto-drafted `rejection_cause`, then rejects) → admin decides → `active` or `rejected` → merchant can restart → `pending`. `is_test=True` means the merchant is an archived E2E/test-run account (excluded from the admin queue + batch-test scoring). `null` risk score means "not yet assessed" — never conflate it with `0`.

3. **Defer, never determine on partial signals.** The LLM and the external sources are *required* signals. If either is unavailable (real outage, or the demo `llm_down`/`sources_down` chaos toggles), verify returns **503**, the merchant stays `submitted`, and a `verification_deferred` audit entry records why. Never score a merchant against silence. OCR extraction failures are different: they are merchant-facing and retry-friendly (`temporarily_unavailable` on the document), never a hard rejection.

4. **No real PII, ever.** All test data in `backend/seed.py` is synthetic and clearly fake-looking on purpose. The 5 "external" tables (`govt_database`, `ckyc_records`, `automated_verification`, `bank_account_validation`, `compliance_reviews`) simulate third-party systems by design — do not wire real government/bank APIs.

5. **Frontend UI is monochrome (black/white/gray) enterprise design**, deliberately not a Razorpay clone. `tailwind.config.js` declares "No custom colors." Keep it that way (teal branding was removed in an earlier session).

6. **Forgot-password is intentionally out of scope.** Auth only supports signup/login.

7. **Append-only audit trail + soft archiving.** Never hard-delete a merchant or document: archive with `is_test=True` / retire with `is_active=False` so history survives. Maintenance cleanups must never archive a real (non-test) account — the discriminator is "has an `expected_outcome` audit entry" (seeded ground truth) vs "created by an E2E run" (doesn't). This bit a real account once (Session 21b) — be careful with cleanup logic.

8. **Admin decisions are single-winner state transitions** (ADR-008). `decide_application` updates via a conditional `UPDATE ... WHERE status IN ('verified_matching','verified_mismatched')` and 409s on a lost race. Don't "simplify" this back to a read-check-write.

## Backend structure (`backend/`, all files flat, no subfolders)

| File | Responsibility |
|---|---|
| `config.py` | All settings/constants/thresholds (risk weights, limits, URLs). Never hardcode a value elsewhere — add it here. |
| `db.py` | SQLAlchemy engine, session, ORM models (app + 5 simulated external tables), `init_db`/`apply_migrations` startup safety nets (idempotent `is_test` column ensure + Alembic stamp/upgrade — no auto-archiving of accounts at boot). |
| `schemas.py` | Pydantic request/response contracts — separate from ORM models on purpose (SRP). |
| `auth.py` | Password hashing (bcrypt via passlib), JWT issue/verify, signup/login, `get_current_merchant` and `require_role` dependencies. |
| `ocr.py` | **Groq vision (qwen)** document-extraction wrapper — typed JSON fields per doc type, retries + backoff + multi-key rotation, PDF rasterization (pypdfium2), blank-image guard. Exposes `extract_structured_fields()`; callers never touch the provider. |
| `verify.py` | LLM calls (Groq/OpenAI-compatible, same key as OCR): `cross_verify_documents` (strict JSON findings), `humanize_reason`, `generate_rejection_cause` — all rephrase-only, never decide/invent. |
| `decision.py` | The deterministic Decision Engine: `check_external_sources` (all 5, no short-circuit), `check_shared_identifiers` (fraud-ring PAN + bank), `compute_risk_score` (single source of truth for scoring), per-document `evaluate` (OCR-confidence path). |
| `documents.py` | Merchant upload/status endpoints; instant per-document format check; sync OCR with retry-friendly `temporarily_unavailable`; sets `submitted` when all 3 docs are valid; `merchant-status` returns docs **newest-first** (so a stale older upload can never shadow the latest one in the UI); restart-application. |
| `admin.py` | Reviewer/admin endpoints: merchant list/detail, `verify_application`, `decide_application` (concurrency-safe), batch-test, maintenance archive, chaos-fault endpoints, risk-eval, system-health. |
| `faults.py` | In-memory demo fault toggles (`ocr_down`, `llm_down`, `sources_down`) — process-local, reset on restart (ADR-007). |
| `health.py` | In-memory sliding-window metrics (OCR/LLM success + latency, HTTP statuses) feeding the system-health view (ADR-007). |
| `risk_eval.py` | Empirical risk-weight calibration: scores the 25 labeled seeded merchants under current weights (replays the real check engine), reports per-class stats + best-F1 cutoff + threshold sweep. |
| `injection_guard.py` | Scans merchant-supplied document text for prompt-injection payloads before it reaches the LLM; redacts flagged values. |
| `main.py` | FastAPI app wiring only (CORS, routers, request-metrics middleware, startup lifespan, test-dataset zip). |
| `seed.py` | Seeds the 5 simulated tables, reviewer/admin demo accounts, and **25 ground-truth labeled merchants** (`expected_outcome` audit entries). |
| `test_features.py` | **Offline E2E suite (59 checks)** via TestClient + throwaway SQLite — covers chaos faults, deferral, calibration, injection defense, concurrency, health, maintenance-archive safety. Run `python test_features.py` from `backend/`. |

**Known constraints:** `passlib==1.7.4` requires `bcrypt==4.0.1` pinned exactly (newer bcrypt breaks passlib). Groq's free tier is ~200K tokens/day **shared by OCR + LLM**; `LLM_FALLBACK_KEYS` from *other* Groq accounts rotate on 401/403/429 (same-account keys add nothing). Extraction requires a vision-capable model (`qwen/qwen3.8-27b` default; gpt-oss models are text-only on Groq).

## Frontend structure (`frontend/src/`)

| File/folder | Responsibility |
|---|---|
| `types.ts` | Every shared TypeScript type (mirrors backend schemas incl. chaos/calibration/health payloads). No `any`. |
| `constants.ts` | API URL, doc slot definitions, `STATUS_LABELS`, `ACTION_LABELS`, `RISK_LEVEL_THRESHOLDS`. |
| `api.ts` | The only file that calls `fetch`. Typed functions per endpoint; components never call the backend directly. |
| `AuthContext.tsx` | Session state (JWT + merchant info) via React context. |
| `components/` | Memoized, accessible pieces: `Button`, `InputField`, `Alert`, `StatusBadge`, `DocumentSlot`, `Layout` (sidebar shell), `RiskBadge`, `RiskBreakdown`, `VerificationTimeline`. |
| `pages/AuthPage.tsx` | Signup/login toggle with demo quick-fill accounts. |
| `pages/DashboardPage.tsx` | Merchant dashboard: 3 document slots, status polling (4s), rejection/restart and activated states. |
| `pages/AdminPage.tsx` | Admin/reviewer panel: fixed-viewport dashboard (page never scrolls — queue table + detail pane scroll internally) with status tabs + merchant table (risk badge), detail panel with verify/decide actions + structured checks + audit trail, and admin-only cards: chaos panel, risk calibration, archive-test-merchants. |
| `App.tsx` | Role-based routing: reviewer/admin → AdminPage, merchant → DashboardPage, no session → AuthPage. |

**Client-side document-type validation is deliberately limited.** The frontend only checks file type/size before upload; real "is this actually a PAN?" validation requires OCR server-side. Don't fake it in the browser.

## How to verify things still work after a change

```bash
cd backend && python -m py_compile *.py        # syntax
cd backend && python test_features.py           # offline E2E suite (no live server, no real API calls — LLM is patched)
cd frontend && npm run typecheck && npm run build
```

`test_features.py` is the fastest full-stack regression signal (auth → upload → verify → decide over the real FastAPI app on a throwaway DB). The live suite is `backend/test_e2e.py` (requires the deployed site + real Groq quota — use sparingly).

## Known limitations (intentional)

- SQLite locally, Postgres in production — selected by `DATABASE_URL` alone (ADR-003).
- No password reset, no websockets (dashboard polls every 4s).
- OCR/LLM metrics and demo faults are process-local — they reset on restart and describe the live instance, not history (ADR-007).
- Real government/CKYC/bank APIs are simulated by 5 seeded tables (by design).
- Groq free-tier daily token quota can be exhausted by heavy testing — surfaces as retry-friendly `temporarily_unavailable`, resets daily.

## If extending this project

- New document type → `config.SUPPORTED_DOCUMENT_TYPES`, the extraction schema map in `ocr.py`, a slot in `frontend/src/constants.ts`.
- New external verification source → ORM model in `db.py`, seed in `seed.py`, check in `decision.check_external_sources()`.
- New risk weight → `config.RISK_WEIGHTS` **and** the mirrored map in `frontend/src/components/RiskBreakdown.tsx` (no shared Python↔TS config — comment both).
- Changing the LLM prompt → `_SYSTEM_PROMPT` in `verify.py`; keep "JSON only, never guess, no approval authority" intact.
- New admin-only panel feature → admin-gated endpoint in `admin.py` + typed function in `api.ts` + card in `AdminPage.tsx`, and log the design call in `docs/adr/` if it's a real decision.
