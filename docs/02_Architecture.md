# System Architecture & Requirements Document
## Merchant Onboarding Copilot
**Version:** 2.0 (kept current — see `session_log.md` for change history)

Covers the system architecture and functional/non-functional requirements in one place. Key design decisions with rationale live in `docs/adr/` (8 records); this document is the map.

---

## 1. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React 18 + TypeScript (Vite), Tailwind CSS (monochrome gray) | Typed data contracts; role-based SPA |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic | One flat, testable service |
| Document extraction | **Groq vision (`qwen/qwen3.8-27b`)** via `ocr.py` wrapper | Vision model returns typed JSON per document in one call; swapped in from OCR.space when that engine proved unreliable (ADR-006) |
| LLM | Groq (`qwen/qwen3.8-27b`), OpenAI-compatible client | Cross-document consistency findings + plain-language rephrasing (never decisions — ADR-001) |
| Database | PostgreSQL (Render, production) / SQLite (local) | Engine selected by `DATABASE_URL` alone (ADR-003) |
| Auth | JWT (PyJWT + passlib/bcrypt) | Simple, role-based (merchant/reviewer/admin) |
| Deployment | Render (backend) + Vercel (frontend); Docker Compose for local | Free-tier hosting; single web process (`WEB_CONCURRENCY=1`) |

## 2. System Components

1. **Frontend app** — signup/login, merchant dashboard (3 document slots), admin/reviewer panel.
2. **API layer (FastAPI)** — `main.py` wiring; routers split by concern: `auth.py`, `documents.py`, `admin.py`.
3. **Extraction Service (`ocr.py`)** — Groq vision → typed fields per doc type; retries/backoff, multi-key rotation, PDF rasterization; exposes one interface (`extract_structured_fields`).
4. **Verification Service (`verify.py`)** — LLM cross-document consistency → structured findings; also humanizes technical reasons (`humanize_reason`, `generate_rejection_cause`) with strict rephrase-only rules.
5. **Decision Engine (`decision.py`)** — deterministic authority: 5 external checks (no short-circuit) + fraud-ring scan + weighted risk score.
6. **Security Guard (`injection_guard.py`)** — scans merchant-supplied text for prompt-injection payloads before the LLM sees it; redacts suspected values.
7. **Mock External Verification Layer** — 5 database tables simulating government DB, CKYC, automated verification, bank validation, compliance reviews.
8. **Audit Log Store** — append-only `audit_logs` table; every meaningful event logged with reason and actor.
9. **Demo/reliability layer** — `faults.py` (process-local outage toggles), `health.py` (rolling OCR/LLM/HTTP metrics), `risk_eval.py` (empirical weight calibration).
10. **Admin panel tooling (admin-only)** — chaos toggles, risk calibration, live system-health, test-merchant archiving.

## 3. Data Flow (current)

### 3.1 Merchant upload → submitted
1. Merchant uploads a document (PAN/GST/BANK_PROOF). Backend validates file type/size, saves the row (`verifying`), then calls `ocr.extract_structured_fields` **synchronously** (ADR-002).
2. On success: fields stored, format signature checked (PAN/GST/IFSC regex on extracted values). On an unreadable/blank file → `invalid_format` (retry same slot). On a service outage → `temporarily_unavailable` (retry-friendly, never a hard rejection).
3. When all 3 documents are format-valid, `onboarding_status` → `submitted`. **No automatic verification runs.**

### 3.2 Admin verification (on demand, `POST /admin/merchants/{id}/verify`)
1. Extracted fields are scanned for prompt-injection payloads (`injection_guard`); suspected values are redacted from the LLM input and audit-logged.
2. **LLM cross-verification** (`verify.cross_verify_documents`) → per-field findings. Required signal: on outage, **defer (503)**, merchant stays `submitted` (ADR-005).
3. **5 external sources** (`decision.check_external_sources`) — all checked unconditionally, each → matched/mismatched `CheckResult`. Required signal: on outage, defer (503).
4. **Fraud-ring scan** (`decision.check_shared_identifiers`) — is this PAN or bank account on any *other* merchant's active documents?
5. Findings merged into `matched_checks`/`mismatched_checks` (stored JSON on the Merchant row), a `prompt_injection_suspected` mismatch is forced if a payload was found, **risk score** computed from weighted mismatches, and status → `verified_matching` (no mismatches) or `verified_mismatched`. Audit: `verification_run` (+ `verification_deferred` / `prompt_injection_suspected` where relevant).

### 3.3 Admin decision (`POST /admin/merchants/{id}/decide`)
1. **Atomic conditional UPDATE** — only a `verified_*` merchant can be decided, and the WHERE clause makes it a single-winner transition (ADR-008); a concurrent second decision gets 409.
2. Approve (one click) → `active`. Reject → `rejected` with a merchant-facing `rejection_reason`: the admin's own note if supplied, else the stored auto-drafted `rejection_cause`. Documents mirror the final call; a `manual_review_resolution` audit entry records actor + decision + note.
3. Merchant dashboard shows the final state; a rejected merchant can restart → `pending`.

### 3.4 Accuracy feedback loops
- `POST /admin/batch-test` — accuracy over the 25 seeded ground-truth merchants (excludes archived `is_test` accounts).
- `POST /admin/risk-eval` — scores the labeled set under current weights: per-class stats, best-F1 cutoff, threshold sweep. Clean mean ≈ 0, flagged mean ≈ 95, F1 = 1.0 at cutoff ≥ 5 on the synthetic set.
- `GET /admin/system-health` — rolling OCR/LLM success rate + latency and HTTP error counts over the last hour (process-local, ADR-007).

## 4. API Design (current)

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/health` | GET | None | Liveness |
| `/auth/signup`, `/auth/login` | POST | None | Account creation / JWT |
| `/documents/upload?doc_type=` | POST | Merchant | Upload → sync extraction + format check |
| `/documents/merchant-status` | GET | Merchant | Status + active documents (**newest-first**) |
| `/documents/restart-application` | POST | Merchant | New application after rejection (409 otherwise) |
| `/admin/merchants` | GET | reviewer/admin | List (status filter, sort-by-risk) |
| `/admin/merchants/{id}` | GET | reviewer/admin | Detail: docs, checks, audit trail |
| `/admin/merchants/{id}/verify` | POST | reviewer/admin | Run LLM + 5 sources + fraud scan (defers on outage) |
| `/admin/merchants/{id}/decide` | POST | reviewer/admin | Mandatory sign-off (single-winner, 409 on conflict) |
| `/admin/batch-test` | POST | admin | Accuracy over seeded ground truth |
| `/admin/faults` + `/admin/faults/{name}` + `/admin/faults/reset` | GET/PUT/POST | admin | Demo outage toggles |
| `/admin/risk-eval` | POST | admin | Empirical weight calibration |
| `/admin/system-health` | GET | admin | Rolling OCR/LLM/HTTP health |
| `/admin/maintenance/clear-test-merchants` | POST | admin | Archive E2E-created merchants (`is_test=True`) |
| `/test-dataset/download` | GET | None | Synthetic test-document zip for judges |

## 5. Authentication & Authorization

- **Authentication:** JWT (HS256) issued at login; merchant + reviewer + admin roles.
- **Authorization rule:** every protected endpoint checks role via `require_role(...)`; merchants can only ever touch their own rows (merchant ID from the token, never from a query param).
- **Permission split:** reviewer → view/verify/decide. Admin → everything above plus chaos toggles, calibration, system-health, maintenance, batch-test. Merchants never see other merchants' data or the internal checks.

## 6. Functional Requirements

| ID | Requirement | Testable acceptance criterion |
|---|---|---|
| FR-1 | Extract typed fields from each uploaded document | Clean PAN image → JSON has `pan_number`, `name`, `dob` |
| FR-2 | Reject a wrong/unreadable document at upload with an actionable status | Aadhaar-in-PAN-slot or blank image → `invalid_format` + message; service outage → `temporarily_unavailable`, not a hard failure |
| FR-3 | Cross-verify fields across documents via LLM, structured findings only | LLM output parsed into `LlmVerificationResult`; LLM never sets a status |
| FR-4 | Check all 5 external sources without short-circuiting | A merchant failing 2 sources reports **both** mismatches |
| FR-5 | Detect shared identifiers across merchant applications | Same PAN/account on 2+ active applications → `fraud_ring_pan`/`fraud_ring_bank` mismatch |
| FR-6 | Compute and store an explainable weighted risk score | `risk_score` = capped weighted sum of mismatches; breakdown renderable per check |
| FR-7 | Human admin must decide every outcome | Only `decide_application` sets `active`/`rejected`; verify never does |
| FR-8 | Defend the LLM against prompt injection from document text | Payload in extracted text is redacted pre-LLM and forces `prompt_injection_suspected` → human review |
| FR-9 | Log every decision + deferral with a reason | Audit rows exist for `verification_run`, `verification_deferred`, `manual_review_resolution`, etc. |
| FR-10 | Batch accuracy + calibration reports | `/admin/batch-test` over 25 records; `/admin/risk-eval` reports stats, cutoff, confusion |
| FR-11 | Survive component outages gracefully | Chaos toggles produce the same retry/defer paths as real outages |
| FR-12 | Never double-process an admin decision | Two concurrent decisions → exactly one succeeds, one 409s, one audit entry |

## 7. Business Rules

- Merchant reaches `submitted` only when all 3 active documents passed their format check. `merchant-status` returns documents newest-first so a stale failed attempt never shadows the latest upload (Session 21b).
- Risk weights (capped at 100): govt_database 30 · ckyc_records 20 · automated_verification 20 · bank_account_validation 20 · compliance_reviews 10 · llm_cross_check 15 (per inconsistent field) · fraud_ring_pan 40 · fraud_ring_bank 40 · prompt_injection_suspected 40. Single source of truth: `decision.compute_risk_score` / `config.RISK_WEIGHTS`.
- LLM and external sources are required signals: unavailable → **defer (503)**, never a partial determination.
- Missing external rows are **mismatches (data)**, not exceptions. An unavailable *service* is an exception (defer).
- A suspected prompt-injection payload always routes to human review — never `verified_matching`.
- `null` risk score = unscored (not verified yet), never displayed as `0`.
- Archived (`is_test=True`) merchants are excluded from the queue and accuracy reports but keep full history (ADR-004).

## 8. Data Requirements

**Document extraction JSON (PAN example):**
```json
{ "doc_type": "PAN", "extracted_fields": { "pan_number": "ABCDE1234F", "name": "Raj Traders", "dob": "1990-01-01" }, "ocr_confidence": 0.95 }
```

**Structured check result (stored on the Merchant row as JSON):**
```json
{ "check_name": "bank_account_validation", "document_type": "BANK_PROOF", "matched": false, "detail": "Bank account not found in validation database" }
```

**Simulated external tables:** `govt_database` (pan), `ckyc_records` (pan), `automated_verification` (pan + check_type), `bank_account_validation` (account + ifsc + name_match_score), `compliance_reviews` (pan + flag_reason).

**Validations:** PAN `[A-Z]{5}[0-9]{4}[A-Z]`, GST `\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]`, IFSC `[A-Z]{4}0[A-Z0-9]{6}`; JPG/PNG/PDF ≤ 5 MB.

## 9. Error Handling & Edge Cases

| Case | Handling |
|---|---|
| Unreadable/blank document | `invalid_format` — merchant retries the same slot |
| Extraction service down / quota exhausted | `temporarily_unavailable` with retry path (after retries + key rotation) |
| LLM down during verify | 503 `verification_deferred`, merchant stays `submitted`, audit-logged |
| External sources down during verify | Same deferral semantics |
| Prompt-injection payload in a document | Sanitized before LLM; forced mismatch → human review; audit-logged |
| Two admins decide the same merchant simultaneously | One wins; loser gets 409; single audit entry (conditional UPDATE) |
| Stale invalid document shadows a new upload | Impossible since Session 21b: documents are listed newest-first |
| Partial field extraction | Fields empty-stringed; LLM marks missing values inconsistent, never guesses |

## 10. Security

- No real PII — all seed data synthetic.
- Secrets via environment variables only (`config.py` / `.env`), never in code.
- Uploads validated (type magic bytes + size); blank/corrupt files rejected early without API calls.
- Prompt-injection defense at the LLM boundary (`injection_guard.py`).
- Role-gated admin endpoints (`require_role("admin")` for maintenance/chaos/calibration/health).
- Passwords bcrypt-hashed (passlib, bcrypt pinned 4.0.1).

## 11. Performance & Reliability

- One external-service call happens per document (sync OCR, ~seconds) and one verify request per merchant — both within a human-driven flow (ADR-002).
- Retries with exponential backoff + multi-key rotation on transient failures.
- Failure-injection mode proves the degradation paths live (`faults.py` + chaos panel).
- Live visibility: `GET /admin/system-health` (OCR/LLM success + avg/p95 latency, HTTP 5xx) — process-local sliding window (ADR-007).

## 12. Deployment

- Render (backend, Dockerfile, Postgres via `DATABASE_URL`, `render.yaml`) + Vercel (frontend). `WEB_CONCURRENCY=1` — single process assumption for `faults.py`/`health.py`.
- Startup order handled in `main.py` lifespan + `seed.py`: init tables → Alembic stamp/upgrade → idempotent seed → upload-dir ensure (deploy failures from missing columns were fixed in Sessions 19–20).
- Docker Compose for one-command local run.

## 13. Scalability Notes (practical, not over-engineered)

- Current design comfortably handles the demo (single human-driven flow) on one instance.
- The documented future path (if this ever scaled) is moving OCR/LLM off the request path into a queue — deliberately *not* built (ADR-002 explains why on Render's free tier). Process-local demo state (`faults.py`, `health.py`) would need replacing on multi-process deployments (ADR-007).
