# Merchant Onboarding Copilot

An automated KYC verification pipeline for merchant onboarding, built for the Razorpay AI Buildathon 2026 (Growth track).

A merchant signs up, uploads PAN / GST / bank-proof documents, and the system automatically extracts, cross-verifies, and checks those documents against simulated external data sources — approving, flagging, or rejecting the merchant without manual review for the clean-path case.

See `docs/` for the full PRD, Architecture, UI/UX, and Development Plan documents.

## Project Structure

```
merchant-onboarding-copilot/
├── docs/                  # PRD, Architecture, UI/UX, Dev Plan
├── backend/               # FastAPI app (auth, OCR, LLM verification, decision engine)
│   └── schema.sql         # Full database schema (reference/importable SQL)
├── frontend/              # React + TypeScript app (signup/login, upload dashboard)
├── docker-compose.yml
├── KNOWLEDGE.md           # project context for AI coding agents / contributors
└── AGENT_INSTRUCTIONS.md  # mandatory coding standards for any future changes
```

**Before making any code changes, your coding agent should read `AGENT_INSTRUCTIONS.md` (mandatory rules) and `KNOWLEDGE.md` (project context) in full.**

## Prerequisites

- Python 3.11+
- Node.js 20+
- A Groq API key (free, no credit card) — get one at [console.groq.com](https://console.groq.com)

## Running locally (without Docker)

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then fill in JWT_SECRET_KEY and LLM_API_KEY (from console.groq.com)
python seed.py                  # populates the 5 mock verification tables + test data
uvicorn main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`. Interactive API docs at `http://localhost:8000/docs`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.

## Running with Docker

```bash
cp backend/.env.example backend/.env   # fill in real values first
docker-compose up --build
```

## Test accounts (created by seed.py)

| Role | Email | Password |
|---|---|---|
| Reviewer | reviewer@example.com | ReviewerPass123 |
| Admin | admin@example.com | AdminPass123 |
| Sample merchants | clean_merchant_0@example.com … clean_merchant_14@example.com | TestPass123 |
| Sample merchants (flagged) | mismatch_merchant_0@example.com … mismatch_merchant_9@example.com | TestPass123 |

## Key Endpoints

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/auth/signup` | POST | none | Create merchant account |
| `/auth/login` | POST | none | Get a JWT |
| `/documents/upload?doc_type=PAN` | POST | merchant | Upload a document |
| `/documents/merchant-status` | GET | merchant | Full onboarding status |
| `/admin/exceptions` | GET | reviewer/admin | List flagged cases |
| `/admin/batch-test` | POST | admin | Accuracy report across seeded test merchants |

## Database Schema

The full schema is in `backend/schema.sql` (auto-generated from the SQLAlchemy models in `backend/db.py`, so it's always accurate). Tables:

- `merchants` — accounts, auth, onboarding status
- `documents` — uploaded documents, OCR results, verification status per merchant
- `audit_logs` — immutable log of every verification decision and why
- `govt_database`, `ckyc_records`, `automated_verification`, `bank_account_validation`, `compliance_reviews` — the 5 simulated external verification sources, seeded with synthetic data by `seed.py`

Running `python seed.py` creates the actual SQLite database file (`backend/app.db`) with these tables and seed data — you don't need to run `schema.sql` manually, it's there for reference/documentation and for importing into a DB tool if you want to inspect the schema visually.

## Important Notes

- **No real PII is used anywhere.** All documents and verification data are synthetic, by design (see PRD Assumptions).
- **PaddleOCR/PaddlePaddle are large dependencies.** First install/build will take time.
- **The LLM never makes the final approve/reject call** — it only proposes findings; `backend/decision.py` is the sole decision-maker. This is intentional (see Architecture doc, Business Rules).

For anything else — architecture rationale, what to change and where — read `KNOWLEDGE.md`.
