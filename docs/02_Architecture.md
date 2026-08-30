# System Architecture & Requirements Document
## Merchant Onboarding Copilot
**Version:** 1.0

This document covers both the system architecture and the detailed functional/non-functional requirements (folded in from the SRS) so decisions and constraints live in one place.

---

## 1. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + TypeScript (Vite), Tailwind CSS | Fast setup, typed data contracts, Razorpay-inspired UI |
| Backend | Python (FastAPI) | Native fit for PaddleOCR + easy async LLM calls |
| OCR | PaddleOCR (PP-OCR detection/recognition pipeline) | Lightweight, handles noisy/rotated document scans well |
| LLM | Claude API | Structured-output cross-verification with strict prompting |
| Database | PostgreSQL (or SQLite for demo simplicity) | Relational fit for merchant records + 5 verification-source tables |
| Auth | JWT-based session auth | Simple, standard, sufficient for demo scope |
| Deployment | Docker Compose (frontend, backend, DB as services) | One-command local/demo deployment |

## 2. System Components

1. **Frontend app** — signup/login, document upload UI, status dashboard
2. **API Gateway (FastAPI)** — single backend service exposing REST endpoints
3. **OCR Service** — wraps PaddleOCR, converts document image/PDF → structured JSON
4. **Verification Service** — calls the LLM with strict prompts, parses structured response
5. **Decision Engine** — deterministic rule layer combining OCR confidence + LLM findings + external-check results into final status
6. **Mock External Verification Layer** — 5 database tables simulating: government database, CKYC records, automated verification systems, bank account validation, compliance reviews
7. **Audit Log Store** — append-only log of every verification decision and its reasoning

## 3. Data Flow

1. Merchant uploads document → frontend runs a lightweight client-side type check (file/image heuristics) before allowing submission
2. Document sent to backend → OCR Service extracts raw text + bounding boxes
3. OCR output normalized into a structured JSON per document type (see Data Requirements)
4. JSON sent to Verification Service → Claude API call with strict prompt → returns structured findings (match/mismatch per field, confidence, reasoning)
5. Decision Engine checks: OCR confidence thresholds + LLM findings + mock external verification results
6. Final decision (approved / rejected / flagged for review) is written to DB with full audit trail
7. Frontend polls/receives status update and displays result to merchant

## 4. API Design (REST)

| Endpoint | Method | Purpose |
|---|---|---|
| `/auth/signup` | POST | Create merchant account |
| `/auth/login` | POST | Authenticate, return JWT |
| `/documents/upload` | POST | Upload a document for a given slot (PAN/GST/Bank) |
| `/documents/{id}/status` | GET | Get verification status of one document |
| `/merchant/{id}/status` | GET | Get overall onboarding status |
| `/admin/exceptions` | GET | List flagged cases (reviewer role only) |
| `/admin/batch-test` | POST | Run the 50-record synthetic batch test, return metrics |

## 5. Authentication & Authorization

- **Authentication:** JWT issued on login, short expiry + refresh token
- **Roles:**
  - `merchant` — can upload own documents, view own status only
  - `reviewer` — can view flagged/exception cases across all merchants, cannot edit documents
  - `admin` — can run batch tests, view all data (demo/testing role)
- **Authorization rule:** every endpoint checks role + ownership (a merchant can only ever query their own merchant ID)

## 6. Functional Requirements

| ID | Requirement | Testable acceptance criteria |
|---|---|---|
| FR-1 | System shall reject a document if it is uploaded into the wrong slot type | Uploading an Aadhaar image into the PAN slot returns a rejection with reason `document_type_mismatch` |
| FR-2 | System shall extract structured fields from each document via OCR | For a clean PAN image, output JSON contains `pan_number`, `name`, `dob` fields non-null |
| FR-3 | System shall cross-verify extracted fields across documents via LLM | Given name "Raj Traders" on PAN and "Raj Enterprises" on GST, the LLM output flags a `name_mismatch` finding |
| FR-4 | System shall not let the LLM directly approve/reject — only propose findings | Decision Engine code path shows LLM output as input only, never as the final status setter |
| FR-5 | System shall check merchant data against 5 mock external sources | Each merchant record has 5 corresponding lookup results (or explicit "not found") before final approval |
| FR-6 | System shall log every decision with a reason | Each merchant status change has a corresponding audit log row with `reason` field populated |
| FR-7 | System shall support a batch-test mode over 50 synthetic records | `/admin/batch-test` returns match rate, false-approval count, and list of unresolved exceptions |

## 7. Business Rules

- A merchant cannot be marked "approved" unless: OCR confidence ≥ threshold for all 3 documents, LLM finds no unresolved mismatches, AND all 5 mock external checks return "verified"
- Any single external check returning "not found" or "mismatch" routes the merchant to `flagged_for_review`, never auto-rejects immediately
- Any document with OCR confidence below threshold requires re-upload before proceeding

## 8. Data Requirements

**Document extraction JSON (example — PAN):**
```json
{
  "doc_type": "PAN",
  "extracted_fields": {
    "pan_number": "ABCDE1234F",
    "name": "Raj Traders",
    "dob": "1990-01-01"
  },
  "ocr_confidence": 0.94
}
```

**Mock verification tables:**

| Table | Key fields |
|---|---|
| `govt_database` | pan_number, name, dob, status |
| `ckyc_records` | ckyc_id, pan_number, kyc_status, last_updated |
| `automated_verification` | merchant_id, check_type, result, confidence |
| `bank_account_validation` | account_no, ifsc, name_match_score, verified |
| `compliance_reviews` | merchant_id, flag_reason, reviewer, status |

## 9. Validations

- PAN format: regex `[A-Z]{5}[0-9]{4}[A-Z]{1}`
- GST format: regex `\d{2}[A-Z]{5}\d{4}[A-Z]{1}\d[Z]{1}[A-Z\d]{1}`
- IFSC format: regex `[A-Z]{4}0[A-Z0-9]{6}`
- File type: only JPG/PNG/PDF accepted, max 5MB
- Name-match validation uses fuzzy string matching (e.g., threshold ≥ 85% similarity) before flagging a mismatch, to tolerate minor OCR noise

## 10. Error Handling & Edge Cases

| Case | Handling |
|---|---|
| Unreadable/blurry document | OCR confidence below threshold → reject with "please re-upload a clearer image" |
| Wrong document type in slot | Rejected at client-side check; also re-validated server-side as a safety net |
| LLM API failure/timeout | Retry once; on repeated failure, route to manual review queue (never silently approve) |
| Partial field extraction (e.g., PAN number missing) | Treated as low confidence → flagged, not auto-approved |
| Conflicting external checks (e.g., CKYC says verified, bank says mismatch) | Always flagged for manual review — conflicts never resolve to auto-approval |

## 11. Security

- No real PII used or stored — all test data synthetic
- JWT secrets and API keys stored in environment variables, never in code
- Uploaded documents stored with restricted access (only owning merchant + reviewer role)
- All external/mock verification calls logged for audit purposes

## 12. Performance

- OCR + LLM verification target: complete within 30 seconds per merchant for the demo dataset
- Batch test of 50 records should complete within a few minutes for a live demo

## 13. Deployment

- Docker Compose: `frontend`, `backend`, `postgres` services
- Environment variables for API keys (Claude API key, JWT secret)
- Single `docker-compose up` for judges/reviewers to run locally if needed

## 14. Monitoring (lightweight, demo-appropriate)

- Structured logging (JSON logs) for every verification step
- A simple `/admin/batch-test` report acts as the "monitoring dashboard" for this MVP — full observability tooling is out of scope

## 15. Scalability Notes (kept practical, not over-engineered)

- Current design handles the demo's synthetic batch easily on a single instance
- If scaled: OCR and LLM calls would move to an async task queue (e.g., Celery/RQ) so uploads don't block on processing — noted as a future improvement, not built for MVP
