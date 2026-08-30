# KNOWLEDGE.md

This file exists so an AI coding agent (or a human joining later) can understand this project's context, decisions, and constraints without re-reading every file. Read this before making changes.

## What this project is

**Merchant Onboarding Copilot** — built for the Razorpay AI Buildathon 2026, Growth track. A merchant uploads PAN, GST, and bank-proof documents; each gets an instant format-validity check (OCR + pattern match) only. Once all 3 pass, the automated pipeline (LLM cross-check + 5 simulated external data sources) runs in the background and produces a **recommendation for an admin**, logged to the audit trail — it never applies directly to the merchant's account. **Every merchant, including ones the automation would recommend approving, requires an explicit admin decision before their account activates.** This is a deliberate design choice (changed from an earlier fully-automated version — see `session_log.md` for when/why) prioritizing a human-in-the-loop compliance pattern over full automation.

Full requirements/design context lives in `docs/`:
- `01_PRD.md` — problem, users, MVP scope, success metrics (note: written for the earlier fully-automated version; the mandatory-admin-decision gate described above supersedes its auto-approval framing — see `session_log.md` for the change)
- `02_Architecture.md` — tech stack, functional requirements, business rules, validations, error handling (this is the SRS content, folded in — there is no separate SRS file by design)
- `03_UIUX.md` — screens, states, design principles
- `04_Development_Plan.md` — build phases and Definition of Done per phase

**Read those before making product/scope decisions**, but treat `session_log.md`'s most recent entries as the source of truth wherever they conflict with the original docs above. This file covers implementation-level context only.

## Non-negotiable design decisions — do not casually change these

1. **The LLM never makes the final approve/reject decision — verification is admin-triggered, never automatic.** `backend/verify.py` calls an LLM (Groq/OpenAI-compatible) and returns structured *findings* only. `backend/decision.py`'s `check_external_sources()` now checks **all 5** external sources unconditionally (no short-circuiting) and returns a structured `VerificationBreakdown` with matched/mismatched `CheckResult` entries. The LLM cross-check and external checks are triggered **on-demand** by an admin clicking "Verify with internal databases" (`POST /admin/merchants/{id}/verify`) — they do NOT run automatically when the 3rd document is uploaded. The only code path that can set `onboarding_status` to `"active"` or `"rejected"` is `admin.py`'s `decide_application()`, triggered by an explicit admin/reviewer action. If you're tempted to have the automated pipeline set a merchant's status directly, don't — this is intentional, not a bug.

2. **A merchant's status flow is: `pending` → `submitted` (all 3 docs format-valid) → admin triggers verify → `verified_matching` or `verified_mismatched` → admin decides → `active` or `rejected`.** After upload, the merchant sits at `"submitted"` until an admin clicks "Verify with internal databases." That runs the LLM cross-check + all 5 external sources and stores a structured breakdown (`matched_checks`/`mismatched_checks`) on the Merchant row. The status becomes `"verified_matching"` (all checks passed → one-click approve) or `"verified_mismatched"` (mismatches found → admin reviews the breakdown and can reject with the auto-generated `rejection_cause`). The merchant is never shown the automated system's technical reasoning directly; only a neutral "under review" message (before a decision) or a humanized reason (after an admin rejects, via `verify.humanize_reason()` or `verify.generate_rejection_cause()`).

3. **No real PII, ever.** All test data (PAN numbers, names, bank accounts) in `backend/seed.py` is synthetic and clearly fake-looking on purpose. Do not wire this project to real government/bank APIs — the 5 "external" tables (`govt_database`, `ckyc_records`, `automated_verification`, `bank_account_validation`, `compliance_reviews`) are simulated by design, per the PRD's explicit scope.

4. **Frontend UI is "Razorpay-inspired," not a clone.** `tailwind.config.js` uses a custom teal palette, deliberately not Razorpay's exact brand tokens/logo. Keep it that way — copying their exact branding is a trademark risk for a public submission.

5. **Forgot-password is intentionally out of scope.** Auth only supports signup/login. Don't add password reset unless the user explicitly asks again.

## Backend structure (`backend/`, all files flat, no subfolders)

| File | Responsibility |
|---|---|
| `config.py` | All settings/constants/thresholds. Never hardcode a value elsewhere — add it here. |
| `db.py` | SQLAlchemy engine, session, and every ORM model (app tables + 5 mock external tables) |
| `schemas.py` | Pydantic request/response contracts — separate from ORM models on purpose (SRP) |
| `auth.py` | Password hashing (bcrypt via passlib), JWT issue/verify, signup/login routes, `get_current_merchant` and `require_role` dependencies |
| `ocr.py` | PaddleOCR wrapper + per-document-type field parsing (PAN/GST/bank proof) |
| `verify.py` | LLM API call (Groq/OpenAI-compatible) for cross-document consistency checking (strict, JSON-only prompt) |
| `decision.py` | The deterministic decision engine + audit logging — the actual "brain" of the system |
| `documents.py` | Upload/status endpoints; instant format check per document; once all 3 are format-valid, sets `onboarding_status = "submitted"` (Phase 3: the LLM/external checks have been moved to admin.py) |
| `admin.py` | Reviewer/admin-only endpoints: merchant list/detail, `verify_application` (admin-triggered LLM + external checks), `decide_application` (the mandatory approve/reject sign-off — the only path to `"active"`), batch-test accuracy report |
| `main.py` | FastAPI app wiring only (CORS, routers, startup) — no business logic belongs here |
| `seed.py` | Populates the 5 mock tables + reviewer/admin accounts + 25 ground-truth-tagged test merchants |

**Known constraint:** `passlib==1.7.4` requires `bcrypt==4.0.1` pinned exactly — newer bcrypt versions break passlib's backend detection and signup will crash with a cryptic error. This was hit and fixed during development; don't upgrade bcrypt without also upgrading passlib (or switching to calling `bcrypt` directly).

## Frontend structure (`frontend/src/`)

| File/folder | Responsibility |
|---|---|
| `types.ts` | Every shared TypeScript type. No `any` anywhere in this codebase — keep it that way. |
| `constants.ts` | All config values (API URL, file limits, document slot definitions, labels) |
| `api.ts` | The only file that calls `fetch`. Components never call the backend directly. |
| `AuthContext.tsx` | Session state (JWT + merchant info) shared app-wide via React context |
| `components/` | Reusable, memoized, accessible pieces: `Button`, `InputField`, `StatusBadge`, `Alert`, `DocumentSlot` |
| `pages/AuthPage.tsx` | Signup/login toggle, client-side validation mirroring backend rules |
| `pages/DashboardPage.tsx` | The 3 document slots, status polling (every 4s), account-activated state |
| `App.tsx` | Routes between `AuthPage`/`DashboardPage` based on session — no router library needed for this linear MVP flow |

**Client-side document-type validation is deliberately limited.** The frontend only checks file type/size before upload — actual document-type matching (e.g. catching an Aadhaar card uploaded to the PAN slot) requires OCR, which happens server-side in `documents.py`. The UI shows that result once the upload response comes back. Don't try to fake this check in the browser with something that isn't real OCR.

## How to verify things still work after a change

Backend (no need to install the heavy `paddleocr`/`paddlepaddle` for basic checks):
```bash
cd backend
python -m py_compile *.py                    # syntax check
python -c "from fastapi.testclient import TestClient; from main import app; ..."  # boot + endpoint check
```

Frontend:
```bash
cd frontend
npm run typecheck   # strict TypeScript, must pass with zero errors
npm run build        # full production build
```

## Known limitations (intentional, per MVP scope in the PRD)

- SQLite by default, not Postgres (swap `DATABASE_URL` in `.env` to change this — no code changes needed)
- No password reset flow
- No real government/CKYC/bank API integration — 5 tables are simulated
- No websockets — dashboard polls every 4 seconds instead
- `_best_guess_name_line()` in `ocr.py` is a simple heuristic; the LLM step is the authority on whether extracted data is trustworthy, not this parser

## If extending this project

- New document type → add to `config.SUPPORTED_DOCUMENT_TYPES`, add a parser function in `ocr.py`, add to `FIELD_PARSERS`, add a slot definition in `frontend/src/constants.ts`
- New external verification source → add an ORM model in `db.py`, seed it in `seed.py`, add a check in `decision.check_external_sources()`
- Changing the LLM prompt → edit `_SYSTEM_PROMPT` in `verify.py`; keep the "JSON only, never guess, no approval authority" rules intact
