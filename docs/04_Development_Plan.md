# Development Plan
## Merchant Onboarding Copilot
**Version:** 2.0 — all original phases shipped (see status note below)

> ## ✅ STATUS: ALL PHASES COMPLETE
>
> Phases 0–7 below (setup → DB → backend core → frontend core → integration → testing → polish → deploy) are **done**. The plan was written when OCR meant PaddleOCR and the LLM meant Claude; the shipped stack uses **Groq vision (qwen) for extraction** and the **same Groq key for LLM verification** (swap documented in `docs/adr/006`), with a mandatory human sign-off (Phase 3 workflow) and no automatic approval path.
>
> **Post-plan additions (Sessions 10–22, see `session_log.md`):** weighted risk scoring + fraud-ring detection, admin-triggered verify/decide states, risk-sorted queue, prompt-injection defense, failure-injection chaos panel, empirical risk-weight calibration, concurrency-safe decisions, live system-health view, test-merchant archiving, and 8 Architecture Decision Records in `docs/adr/`. The current authoritative references are `KNOWLEDGE.md` and `docs/02_Architecture.md`.

---

## 1. Roadmap Overview (as originally planned)

Built to be executable without guessing — each phase has a clear priority, dependency, and Definition of Done (DoD).

| Phase | Focus | Depends on |
|---|---|---|
| 0 | Setup | — |
| 1 | Database + mock data | Phase 0 |
| 2 | Backend core (OCR + LLM + Decision Engine) | Phase 1 |
| 3 | Frontend core (upload + dashboard) | Phase 0 (can run parallel to Phase 2) |
| 4 | Integration (frontend ↔ backend) | Phase 2 + 3 |
| 5 | Testing (batch test, edge cases) | Phase 4 |
| 6 | Bug fixing & polish | Phase 5 |
| 7 | Deployment & demo prep | Phase 6 |

## 2. Phase 0 — Setup (Priority: Highest)

- Initialize repo structure: `frontend/` (React + TS + Vite), `backend/` (FastAPI)
- Set up Docker Compose skeleton (frontend, backend, postgres)
- Set up environment variable handling (Claude API key, JWT secret, DB URL)

**DoD:** `docker-compose up` starts all 3 services with placeholder "hello world" responses.

## 3. Phase 1 — Database + Mock Data (Priority: High)

- Design and create tables: `merchants`, `documents`, `audit_log`, plus the 5 mock verification tables (`govt_database`, `ckyc_records`, `automated_verification`, `bank_account_validation`, `compliance_reviews`)
- Seed each mock table with ~15–20 rows: mix of clean matches and deliberate mismatches
- Seed 50 synthetic merchant test records for the batch test (Phase 5)

**DoD:** All tables exist with seed data; a query against any mock table returns expected rows for at least one known-good and one known-bad merchant ID.

## 4. Phase 2 — Backend Core (Priority: High)

**2a. OCR Service**
- Integrate PaddleOCR for text detection + recognition
- Build a parser that converts raw OCR output into the structured JSON schema (per document type)

**2b. LLM Verification Service**
- Write the strict cross-verification prompt (structured JSON output, explicit "do not guess" instructions, confidence + reasoning per finding)
- Integrate Claude API call, parse structured response

**2c. Decision Engine**
- Implement deterministic rules combining OCR confidence + LLM findings + mock external check results
- Implement audit logging for every decision

**DoD:** Given a sample document, the pipeline returns a structured decision (approved/flagged/rejected) with a logged reason — testable via a script, no frontend needed yet.

## 5. Phase 3 — Frontend Core (Priority: High, parallel to Phase 2)

- Build signup/login screens
- Build onboarding dashboard with 3 document slots
- Build upload modal with client-side type pre-check
- Build status badges and reason panel components

**DoD:** A user can sign up, see the dashboard, and upload a file into each slot with a mock/local validation response (before real backend integration).

## 6. Phase 4 — Integration (Priority: High)

- Connect frontend upload flow to `/documents/upload` endpoint
- Connect dashboard polling to `/documents/{id}/status` and `/merchant/{id}/status`
- Connect reviewer panel to `/admin/exceptions`

**DoD:** End-to-end flow works live: upload real (synthetic) documents through the UI and see real backend-driven status updates.

## 7. Phase 5 — Testing (Priority: High)

- Run the 50-record batch test via `/admin/batch-test`
- Manually test edge cases: wrong document type, blurry image, mismatched names, all-external-checks-fail case
- Verify audit log completeness for every test case

**DoD:** Batch test report generated with accuracy %, false-approval rate (target 0%), and a clear exception list. All edge cases produce the expected, non-silent outcome.

## 8. Phase 6 — Bug Fixing & Polish (Priority: Medium)

- Fix issues found in Phase 5
- Polish UI states (loading, error, empty) for demo smoothness
- Tighten LLM prompt if any hallucination/false-positive patterns are found in testing

**DoD:** No known false-approval cases remain; UI has no dead-end states.

## 9. Phase 7 — Deployment & Demo Prep (Priority: Medium)

- Finalize Docker Compose for one-command run
- Prepare the 5-minute pitch: problem → architecture → live demo → batch metrics → what broke and how it was fixed
- Push clean code + README to GitHub

**DoD:** A judge can clone the repo, run `docker-compose up`, and reproduce the demo; pitch video recorded.

## 10. MVP Scope Recap

Only these are required to call the MVP "done":
- 3 document types, synthetic data only
- End-to-end upload → OCR → LLM → mock external check → decision → audit log
- Batch test reporting accuracy metrics
- Basic merchant + reviewer UI

Everything else (multi-language, real API integration, video KYC, advanced monitoring) is explicitly deferred — see PRD's Out of Scope section.
