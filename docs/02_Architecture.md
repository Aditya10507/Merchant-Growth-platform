# System Architecture and Requirements
## Merchant Onboarding Copilot
**Version:** 2.0 (kept current; see `session_log.md` for change history)

This document covers the system architecture and the functional and non-functional requirements in one place. The reasoning behind key design decisions lives in `docs/adr/` (8 records). This document is the map of how it all fits together.

---

## 1. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React 18 + TypeScript (Vite), Tailwind CSS (monochrome gray) | Typed data contracts; role-based single-page app |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic | One flat, testable service |
| Document extraction | Groq vision (`qwen/qwen3.8-27b`) through the `ocr.py` wrapper | The vision model returns typed JSON per document in one call. It replaced OCR.space after that engine proved unreliable (ADR-006) |
| LLM | Groq (`qwen/qwen3.8-27b`), OpenAI-compatible client | Cross-document consistency findings and plain-language rewording. It never makes decisions (ADR-001) |
| Database | PostgreSQL (Render, production) / SQLite (local) | Engine chosen by `DATABASE_URL` alone (ADR-003) |
| Auth | JWT (PyJWT + passlib/bcrypt) | Simple, role-based access (merchant/reviewer/admin) |
| Deployment | Render (backend) + Vercel (frontend); Docker Compose for local | Free-tier hosting; single web process (`WEB_CONCURRENCY=1`) |

## 2. System Components

1. **Frontend app.** Signup and login, merchant dashboard with 3 document slots, and the admin or reviewer panel.
2. **API layer (FastAPI).** `main.py` wires everything together; routers are split by concern in `auth.py`, `documents.py`, and `admin.py`.
3. **Extraction Service (`ocr.py`).** Groq vision turns each document into typed fields. It handles retries, backoff, multi-key rotation, and PDF rasterization, and exposes one interface (`extract_structured_fields`).
4. **Verification Service (`verify.py`).** Groq cross-checks document consistency and returns structured findings. It also rewrites technical reasons into plain language (`humanize_reason`, `generate_rejection_cause`) under strict rephrase-only rules.
5. **Decision Engine (`decision.py`).** The deterministic authority. It runs 5 external checks without short-circuiting, a fraud-ring scan, and the weighted risk score.
6. **Security Guard (`injection_guard.py`).** Scans merchant-supplied text for prompt-injection payloads before the LLM sees it and redacts suspected values.
7. **Mock External Verification Layer.** 5 database tables that simulate a government database, CKYC, automated verification, bank validation, and compliance reviews.
8. **Audit Log Store.** An append-only `audit_logs` table. Every meaningful event is logged with a reason and an actor.
9. **Demo and reliability layer.** `faults.py` (process-local outage toggles), `health.py` (rolling OCR/LLM/HTTP metrics), and `risk_eval.py` (empirical weight calibration).
10. **Admin panel (admin-only).** A simple review queue with Applicants, Active merchants, and Rejected tabs, plus a stationary detail pane for verify, fraud-ring analysis, and accept or reject. Chaos toggles, risk calibration, system health, and test-merchant archiving stay as admin-only endpoints and are not shown in the UI (Session 26).

## 3. Data Flow (current)

### 3.1 Merchant upload to submitted
1. A merchant uploads a document (PAN, GST, or BANK_PROOF). The backend validates file type and size, saves the row (`verifying`), then calls `ocr.extract_structured_fields` synchronously (ADR-002).
2. On success, fields are stored and a format check runs (PAN/GST/IFSC regex against the extracted values). An unreadable or blank file becomes `invalid_format` (retry the same slot). A service outage becomes `temporarily_unavailable` (retry-friendly, never a hard rejection).
3. When all 3 documents pass their format check, `onboarding_status` becomes `submitted`. No automatic verification runs.

### 3.2 Admin verification (on demand, `POST /admin/merchants/{id}/verify`)
1. Extracted fields are scanned for prompt-injection payloads (`injection_guard`). Suspected values are redacted from the LLM input and audit-logged.
2. **LLM cross-verification** (`verify.cross_verify_documents`) returns per-field findings. This is a required signal: on outage, verification defers with a 503 and the merchant stays `submitted` (ADR-005).
3. **5 external sources** (`decision.check_external_sources`) are all checked unconditionally. Each returns a matched or mismatched `CheckResult`. This is also a required signal: on outage, verification defers (503).
4. **Fraud-ring scan** (`decision.check_shared_identifiers`) asks whether this PAN or bank account appears on any other merchant's active documents.
5. Findings are merged into `matched_checks` and `mismatched_checks` (JSON stored on the Merchant row). If a payload was found, a `prompt_injection_suspected` mismatch is forced. The risk score is computed from weighted mismatches and the status moves to `verified_matching` (no mismatches) or `verified_mismatched`. Audit entries: `verification_run`, plus `verification_deferred` or `prompt_injection_suspected` where relevant.

### 3.3 Admin decision (`POST /admin/merchants/{id}/decide`)
1. **Atomic conditional UPDATE.** Only a `verified_*` merchant can be decided, and the WHERE clause makes it a single-winner transition (ADR-008). A concurrent second decision gets a 409.
2. Approve (one click) moves the merchant to `active`. Reject moves it to `rejected` with a merchant-facing `rejection_reason`: the admin's own note if supplied, otherwise the stored auto-drafted `rejection_cause`. Documents mirror the final call. A `manual_review_resolution` audit entry records the actor, decision, and note.
3. The merchant dashboard shows the final state. A rejected merchant can restart, returning to `pending`.

### 3.4 Accuracy feedback loops
- `POST /admin/batch-test`: accuracy over the 25 seeded ground-truth merchants (archived `is_test` accounts are excluded).
- `POST /admin/risk-eval`: scores the labeled set under current weights and reports per-class stats, the best-F1 cutoff, and a threshold sweep. On the synthetic set: clean mean about 0, flagged mean about 95, F1 = 1.0 at a cutoff of 5 or more.
- `GET /admin/system-health`: rolling OCR/LLM success rate and latency plus HTTP error counts over the last hour (process-local, ADR-007).

## 4. API Design (current)

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/health` | GET | None | Liveness |
| `/auth/signup`, `/auth/login` | POST | None | Account creation / JWT |
| `/documents/upload?doc_type=` | POST | Merchant | Upload with synchronous extraction and format check |
| `/documents/merchant-status` | GET | Merchant | Status and active documents (newest first) |
| `/documents/restart-application` | POST | Merchant | New application after rejection (409 otherwise) |
| `/admin/merchants` | GET | reviewer/admin | List with status filter, sorted by risk |
| `/admin/merchants/{id}` | GET | reviewer/admin | Detail: documents, checks, audit trail |
| `/admin/merchants/{id}/verify` | POST | reviewer/admin | Run LLM + 5 sources + fraud scan (defers on outage) |
| `/admin/merchants/{id}/decide` | POST | reviewer/admin | Mandatory sign-off (single-winner, 409 on conflict) |
| `/admin/stats` | GET | admin | Real-time dashboard counters |
| `/admin/batch-test` | POST | admin | Accuracy over seeded ground truth |
| `/admin/faults`, `/admin/faults/{name}`, `/admin/faults/reset` | GET/PUT/POST | admin | Demo outage toggles |
| `/admin/risk-eval` | POST | admin | Empirical weight calibration |
| `/admin/system-health` | GET | admin | Rolling OCR/LLM/HTTP health |
| `/admin/maintenance/clear-test-merchants` | POST | admin | Archive E2E-created merchants (`is_test=True`) |
| `/test-dataset/download` | GET | None | Synthetic test-document zip for judges |

## 5. Authentication and Authorization

- **Authentication.** JWT (HS256) issued at login. Roles: merchant, reviewer, admin.
- **Authorization rule.** Every protected endpoint checks role through `require_role(...)`. Merchants can only ever touch their own rows (the merchant ID comes from the token, never from a query parameter).
- **Permission split.** Reviewer: view, verify, decide. Admin: everything above plus chaos toggles, calibration, system health, maintenance, and batch test. Merchants never see other merchants' data or the internal checks.

## 6. Functional Requirements

| ID | Requirement | Testable acceptance criterion |
|---|---|---|
| FR-1 | Extract typed fields from each uploaded document | Clean PAN image returns JSON with `pan_number`, `name`, `dob` |
| FR-2 | Reject a wrong or unreadable document at upload with an actionable status | Aadhaar in the PAN slot or a blank image gives `invalid_format` with a message; a service outage gives `temporarily_unavailable`, not a hard failure |
| FR-3 | Cross-verify fields across documents via LLM, structured findings only | LLM output parses into `LlmVerificationResult`; the LLM never sets a status |
| FR-4 | Check all 5 external sources without short-circuiting | A merchant failing 2 sources reports both mismatches |
| FR-5 | Detect identifiers shared across merchant applications | Same PAN or account on 2+ active applications gives `fraud_ring_pan` or `fraud_ring_bank` mismatch |
| FR-6 | Compute and store an explainable weighted risk score | `risk_score` is a capped weighted sum of mismatches; the breakdown is renderable per check |
| FR-7 | Human admin must decide every outcome | Only `decide_application` sets `active` or `rejected`; verification never does |
| FR-8 | Defend the LLM against prompt injection from document text | A payload in extracted text is redacted before the LLM and forces `prompt_injection_suspected`, routing to human review |
| FR-9 | Log every decision and deferral with a reason | Audit rows exist for `verification_run`, `verification_deferred`, `manual_review_resolution`, etc. |
| FR-10 | Batch accuracy and calibration reports | `/admin/batch-test` over 25 records; `/admin/risk-eval` reports stats, cutoff, confusion |
| FR-11 | Survive component outages gracefully | Failure toggles produce the same retry and defer paths as real outages |
| FR-12 | Never double-process an admin decision | Two concurrent decisions produce exactly one success, one 409, and one audit entry |

## 7. Business Rules

- A merchant reaches `submitted` only when all 3 active documents passed their format check. `merchant-status` returns documents newest first so a stale failed attempt never shadows the latest upload (Session 21b).
- Risk weights (capped at 100): govt_database 30, ckyc_records 20, automated_verification 20, bank_account_validation 20, compliance_reviews 10, llm_cross_check 15 per inconsistent field, fraud_ring_pan 40, fraud_ring_bank 40, prompt_injection_suspected 40. The single source of truth is `decision.compute_risk_score` / `config.RISK_WEIGHTS`.
- The LLM and external sources are required signals. If either is unavailable, verification defers with a 503. The system never makes a partial determination.
- A missing external row is a mismatch (data problem), not an exception. An unavailable service is an exception and defers.
- A suspected prompt-injection payload always routes to human review, never to `verified_matching`.
- A `null` risk score means "not yet assessed" and is never displayed as 0.
- Archived merchants (`is_test=True`) are excluded from the queue and accuracy reports but keep their full history (ADR-004).

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

**Validations:** PAN `[A-Z]{5}[0-9]{4}[A-Z]`, GST `\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]`, IFSC `[A-Z]{4}0[A-Z0-9]{6}`. Uploads: JPG/PNG/PDF up to 5 MB.

## 9. Error Handling and Edge Cases

| Case | Handling |
|---|---|
| Unreadable or blank document | `invalid_format`; the merchant retries the same slot |
| Extraction service down or quota exhausted | `temporarily_unavailable` with a retry path (after retries and key rotation) |
| LLM down during verify | 503 `verification_deferred`; the merchant stays `submitted`; audit-logged |
| External sources down during verify | Same deferral behavior |
| Prompt-injection payload in a document | Sanitized before the LLM; forced mismatch routes to human review; audit-logged |
| Two admins decide the same merchant at once | One wins; the loser gets a 409; a single audit entry (conditional UPDATE) |
| Stale invalid document shadows a new upload | Impossible since Session 21b: documents are listed newest first |
| Partial field extraction | Empty fields are emptied; the LLM marks missing values as inconsistent and never guesses |

## 10. Security

- No real personal information. All seed data is synthetic.
- Secrets come from environment variables only (`config.py` / `.env`), never from code.
- Uploads are validated (type magic bytes and size). Blank or corrupt files are rejected early without any API call.
- Prompt-injection defense sits at the LLM boundary (`injection_guard.py`).
- Admin endpoints are role-gated (`require_role("admin")` for maintenance, chaos, calibration, and health).
- Passwords are bcrypt-hashed (passlib, bcrypt pinned 4.0.1).

## 11. Performance and Reliability

- One external-service call per document (synchronous OCR, a few seconds) and one verify request per merchant. Both fit inside a human-driven flow (ADR-002).
- Retries with exponential backoff and multi-key rotation on transient failures.
- Failure-injection mode proves the degradation paths live (`faults.py`).
- Live visibility: `GET /admin/system-health` reports OCR/LLM success and latency plus HTTP 5xx counts from a process-local sliding window (ADR-007).

## 12. Deployment

- Render hosts the backend (Dockerfile, PostgreSQL via `DATABASE_URL`, `render.yaml`). Vercel hosts the frontend. `WEB_CONCURRENCY=1` keeps a single process, which `faults.py` and `health.py` assume.
- Startup order is handled in `main.py` lifespan and `seed.py`: create tables, stamp or upgrade Alembic, run an idempotent seed, and ensure the upload directory exists. (Deploy failures from missing columns were fixed in Sessions 19-20.)
- Docker Compose provides a one-command local run.

## 13. Scalability Notes (practical, not over-engineered)

- The current design comfortably handles the demo, a single human-driven flow, on one instance.
- The documented future path, if this ever scales, is moving OCR and LLM work off the request path into a queue. That was deliberately not built (ADR-002 explains why on Render's free tier). Process-local demo state (`faults.py`, `health.py`) would need replacing on multi-process deployments (ADR-007).
