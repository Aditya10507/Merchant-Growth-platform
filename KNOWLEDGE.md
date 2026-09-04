# KNOWLEDGE.md

This file exists so an AI coding agent (or a human joining later) can understand this project's context, decisions, and constraints without re-reading every file. Read this before making changes.

## What this project is

**Merchant Onboarding Copilot**, built for the Razorpay AI Buildathon 2026 ("AI Risk Manager" track). A merchant signs up and uploads PAN, GST, and bank proof documents. The system extracts typed fields with Groq vision, runs a deterministic verification pipeline (LLM cross-document consistency, 5 simulated external data sources, and a cross-merchant fraud-ring scan), computes a weighted risk score (0 to 100), and presents the full structured breakdown to a human admin who makes the mandatory final approve or reject decision. Nothing ever activates a merchant without an explicit admin sign-off. This human-in-the-loop design is deliberate for compliance.

The buildathon brief is to identify, assess, prioritize, or explain risk. Every feature maps to that: mismatch and fraud detection (identify), risk score (assess), risk-sorted queue (prioritize), audit trail and per-check breakdown (explain). Growth, marketing, and payment features are off-track. Reliability, explainability, and audit-trail work is always on-track.

Full design context:
- `docs/adr/` holds the Architecture Decision Records (8). They explain the "why" behind key design calls: the LLM never decides, synchronous OCR over queues, SQLite to Postgres, defer on partial signals, the vision-OCR swap, atomic decisions, and more. Read these before changing a core design.
- `docs/01_PRD.md`, `docs/02_Architecture.md`, and `docs/03_UIUX.md` cover the product, the architecture and requirements, and the UI/UX. They are kept current.
- `session_log.md` is the chronological record of every session and is the source of truth when anything conflicts.

## Non-negotiable design decisions, do not casually change these

1. **The LLM never makes the final approve or reject decision, and verification is admin-triggered, never automatic.** `verify.py` calls Groq and returns structured findings only. `decision.py` is the deterministic authority. `verify_application()` (the admin's "Verify with internal databases" click, `POST /admin/merchants/{id}/verify`) runs the LLM cross-check, all 5 external sources, and the fraud-ring scan on demand, then stores a structured `matched_checks` / `mismatched_checks` breakdown. The only code path that sets `onboarding_status` to `active` or `rejected` is `decide_application()` (`POST /admin/merchants/{id}/decide`), an explicit admin action. If you are tempted to have any automated path set a merchant's status directly, do not.

2. **The merchant status machine is:** `pending`, then `submitted` (all 3 documents format-valid, no auto-verification), then the admin triggers verify, then `verified_matching` (all checks passed, one-click approve) or `verified_mismatched` (mismatches found, admin reviews the breakdown, may edit the auto-drafted `rejection_cause`, then rejects), then the admin decides, giving `active` or `rejected`, and a rejected merchant can restart back to `pending`. `is_test=True` means the merchant is an archived E2E or test-run account (excluded from the admin queue and batch-test scoring). A `null` risk score means "not yet assessed"; never treat it as 0.

3. **Defer, never determine on partial signals.** The LLM and the external sources are required signals. If either is unavailable (a real outage, or the demo `llm_down` or `sources_down` toggles), verify returns a 503, the merchant stays `submitted`, and a `verification_deferred` audit entry records why. Never score a merchant against silence. OCR extraction failures are different: they are merchant-facing and retry-friendly (`temporarily_unavailable` on the document), never a hard rejection.

4. **No real personal information, ever.** All test data in `backend/seed.py` is synthetic and clearly fake-looking on purpose. The 5 external tables (`govt_database`, `ckyc_records`, `automated_verification`, `bank_account_validation`, `compliance_reviews`) simulate third-party systems by design. Do not wire real government or bank APIs.

5. **The frontend UI is monochrome (black/white/gray) enterprise design**, deliberately not a Razorpay clone. `tailwind.config.js` declares "No custom colors." Keep it that way.

6. **Forgot-password is intentionally out of scope.** Auth only supports signup and login.

7. **Append-only audit trail plus soft archiving.** Never hard-delete a merchant or document. Archive with `is_test=True` or retire with `is_active=False` so history survives. Maintenance cleanups must never archive a real (non-test) account. The discriminator is whether the account has an `expected_outcome` audit entry (seeded ground truth) or was created by an E2E run (no such entry). This bit a real account once (Session 21b), so be careful with cleanup logic.

8. **Admin decisions are single-winner state transitions** (ADR-008). `decide_application` updates via a conditional `UPDATE ... WHERE status IN ('verified_matching','verified_mismatched')` and returns a 409 on a lost race. Do not "simplify" this back into a read-check-write.

## Backend structure (`backend/`, all files flat, no subfolders)

| File | Responsibility |
|---|---|
| `config.py` | All settings, constants, and thresholds (risk weights, limits, URLs). Never hardcode a value elsewhere; add it here. |
| `db.py` | SQLAlchemy engine, session, ORM models (app plus 5 simulated external tables), and `init_db` / `apply_migrations` startup safety nets (idempotent `is_test` column ensure plus Alembic stamp or upgrade; no auto-archiving of accounts at boot). |
| `schemas.py` | Pydantic request and response contracts, separate from ORM models on purpose (single responsibility). |
| `auth.py` | Password hashing (bcrypt via passlib), JWT issue and verify, signup and login, and the `get_current_merchant` and `require_role` dependencies. |
| `ocr.py` | Groq vision (qwen) document extraction wrapper. Typed JSON fields per document type, retries plus backoff plus multi-key rotation, PDF rasterization (pypdfium2), blank-image guard. Exposes `extract_structured_fields()`; callers never touch the provider. |
| `verify.py` | LLM calls (Groq / OpenAI-compatible, same key as OCR): `cross_verify_documents` (strict JSON findings), `humanize_reason`, `generate_rejection_cause`. All are rephrase-only; they never decide or invent. |
| `decision.py` | The deterministic Decision Engine: `check_external_sources` (all 5, no short-circuit), `check_shared_identifiers` (fraud-ring PAN and bank), `compute_risk_score` (single source of truth for scoring), and per-document `evaluate` (OCR-confidence path). |
| `documents.py` | Merchant upload and status endpoints. Instant per-document format check. Synchronous OCR with retry-friendly `temporarily_unavailable`. Sets `submitted` when all 3 documents are valid. Re-upload retires the previous same-type document (no pile-up). `merchant-status` returns documents newest first and self-heals `temporarily_unavailable` documents by re-running OCR after `OCR_STATUS_RETRY_COOLDOWN_SECONDS`, so a transient outage recovers automatically. Also handles restart-application. |
| `admin.py` | Reviewer and admin endpoints: merchant list and detail, `verify_application`, `decide_application` (concurrency-safe), batch test, maintenance archive, failure toggles, risk-eval, system health, and real-time stats. |
| `faults.py` | In-memory demo fault toggles (`ocr_down`, `llm_down`, `sources_down`). Process-local, reset on restart (ADR-007). |
| `health.py` | In-memory sliding-window metrics (OCR/LLM success and latency, HTTP statuses) that feed the system-health view (ADR-007). |
| `risk_eval.py` | Empirical risk-weight calibration: scores the 25 labeled seeded merchants under current weights (replays the real check engine) and reports per-class stats, best-F1 cutoff, and a threshold sweep. |
| `injection_guard.py` | Scans merchant-supplied document text for prompt-injection payloads before it reaches the LLM and redacts flagged values. |
| `main.py` | FastAPI app wiring only: CORS, routers, request-metrics middleware, startup lifespan, test-dataset zip. |
| `seed.py` | Seeds the 5 simulated tables, reviewer and admin demo accounts, and 25 ground-truth labeled merchants (with `expected_outcome` audit entries). |
| `test_features.py` | The offline E2E suite (83 checks) via TestClient plus throwaway SQLite. Covers chaos faults, deferral, calibration, injection defense, concurrency, health, maintenance-archive safety, re-upload retirement, comma-separated status filter, self-healing OCR retry, live admin stats, LLM key rotation, and clean audit trail. Run `python test_features.py` from `backend/`. |

**Known constraints:** `passlib==1.7.4` requires `bcrypt==4.0.1` pinned exactly (newer bcrypt breaks passlib). Groq's free tier is about 200K tokens per day, shared by OCR and LLM. `LLM_FALLBACK_KEYS` from other Groq accounts rotate on 401/403/429 (same-account keys add nothing). Extraction requires a vision-capable model (`qwen/qwen3.8-27b` is the default; gpt-oss models are text-only on Groq).

## Frontend structure (`frontend/src/`)

| File/folder | Responsibility |
|---|---|
| `types.ts` | Every shared TypeScript type (mirrors backend schemas). No `any`. |
| `constants.ts` | API URL, document slot definitions, `STATUS_LABELS`, `ACTION_LABELS`, `RISK_LEVEL_THRESHOLDS`. |
| `api.ts` | The only file that calls `fetch`. Typed functions per endpoint; components never call the backend directly. |
| `AuthContext.tsx` | Session state (JWT and merchant info) via React context. |
| `components/` | Memoized, accessible pieces: `Button`, `InputField`, `Alert`, `StatusBadge`, `DocumentSlot`, `Layout` (sidebar shell), `RiskBadge`, `RiskBreakdown`, `VerificationTimeline`. |
| `pages/AuthPage.tsx` | Signup and login toggle with demo quick-fill accounts. |
| `pages/DashboardPage.tsx` | Merchant dashboard: 3 document slots, status polling (4s), rejection and restart states, activated state. |
| `pages/AdminPage.tsx` | Admin and reviewer panel: fixed-viewport dashboard (the page never scrolls; the queue table and detail pane scroll internally) with a real-time stats strip on top (applicants, approvals, rejections, fraud-ring rate, flagged percentage; polls `/admin/stats` every few seconds and refreshes after every action) and three simple tabs (Applicants, Active merchants, Rejected, driven by a comma-separated `status_filter`), a merchant table with a risk badge, and a stationary detail pane: verify documents, then fraud-ring analysis, verification checks, and risk breakdown, then accept or reject (the decision message flows to the merchant dashboard). No engineering cards in the UI; chaos, calibration, and health stay as backend endpoints and API docs. |
| `App.tsx` | Role-based routing: reviewer or admin goes to AdminPage, merchant goes to DashboardPage, no session goes to AuthPage. |

**Client-side document-type validation is deliberately limited.** The frontend only checks file type and size before upload. Real "is this actually a PAN?" validation requires OCR server-side. Do not fake it in the browser.

## How to verify things still work after a change

```bash
cd backend && python -m py_compile *.py        # syntax
cd backend && python test_features.py           # offline E2E suite (no live server, no real API calls; the LLM is patched)
cd frontend && npm run typecheck && npm run build
```

`test_features.py` is the fastest full-stack regression signal (auth, upload, verify, decide over the real FastAPI app on a throwaway DB). The live suite is `backend/test_e2e.py` (requires the deployed site and real Groq quota; use sparingly).

## Known limitations (intentional)

- SQLite locally, Postgres in production, chosen by `DATABASE_URL` alone (ADR-003).
- No password reset, no websockets (the dashboard polls every 4 seconds).
- OCR/LLM metrics and demo faults are process-local. They reset on restart and describe the live instance, not history (ADR-007).
- Real government/CKYC/bank APIs are simulated by 5 seeded tables (by design).
- Groq free-tier daily token quota can be exhausted by heavy testing. It surfaces as a retry-friendly `temporarily_unavailable` and resets daily.

## If extending this project

- New document type: add it to `config.SUPPORTED_DOCUMENT_TYPES`, the extraction schema map in `ocr.py`, and a slot in `frontend/src/constants.ts`.
- New external verification source: add an ORM model in `db.py`, seed data in `seed.py`, and a check in `decision.check_external_sources()`.
- New risk weight: update `config.RISK_WEIGHTS` and the mirrored map in `frontend/src/components/RiskBreakdown.tsx` (there is no shared Python-to-TypeScript config; comment both).
- Changing the LLM prompt: edit `_SYSTEM_PROMPT` in `verify.py`. Keep "JSON only, never guess, no approval authority" intact.
- New admin-only panel feature: add an admin-gated endpoint in `admin.py`, a typed function in `api.ts`, and the UI in `AdminPage.tsx`. Log the design call in `docs/adr/` if it is a real decision.
