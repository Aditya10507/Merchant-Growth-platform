# Product Requirements Document (PRD)
## Merchant Onboarding Copilot
**Track:** Growth | Razorpay AI Buildathon 2026
**Version:** 1.0

---

## 1. Problem Statement

Merchant onboarding on payment platforms today is slow and error-prone because KYC documents (PAN, GST certificate, bank proof) are manually reviewed by human ops teams or checked with brittle rule-based systems. This causes:

- Long onboarding turnaround time (days instead of minutes)
- Inconsistent verification quality (human fatigue, missed mismatches)
- Poor merchant experience — no real-time feedback on document errors
- High operational cost for the platform (manual review teams)

**Core problem:** There is no fast, accurate, self-explainable way to verify a merchant's identity documents at submission time and cross-check them against internal and external records — without waiting on a human reviewer for every case.

## 2. Target Users

| User | Description | Needs |
|---|---|---|
| **Merchant (primary)** | A business owner signing up to accept payments | Fast, transparent onboarding; clear errors if something's wrong |
| **Compliance/Ops reviewer (secondary)** | Internal team member who handles exceptions | Only wants to see flagged, high-risk cases — not every submission |
| **Platform (Razorpay, in this simulation)** | The business running onboarding | Wants high verification accuracy, full audit trail, low manual load |

## 3. Goals

1. Automatically verify merchant-submitted KYC documents with high accuracy.
2. Reduce onboarding time from days to minutes for the majority of clean submissions.
3. Catch document-type errors (e.g., Aadhaar submitted in the PAN slot) before they even reach backend processing.
4. Provide a transparent, auditable reason for every approval or rejection.
5. Demonstrate a realistic, extensible verification pipeline (OCR → LLM → external checks) that mirrors how a real fintech platform would automate onboarding.

## 4. Core Features (MVP)

1. **Merchant signup/login** (simplified auth flow)
2. **Document upload with slot-specific validation** (PAN slot, GST slot, Bank proof slot)
3. **Client-side document-type pre-check** — reject obviously wrong document types at upload time
4. **OCR extraction** — extract text fields from uploaded documents into structured JSON
5. **LLM cross-verification** — check consistency of extracted fields (name match across docs, valid formats, etc.) using a strict, low-hallucination prompt
6. **Simulated external verification** — check extracted data against 5 mock "external" data sources (government DB, CKYC, automated verification, bank validation, compliance review)
7. **Decision engine** — deterministic rules combine LLM output + external checks to approve, reject, or flag for manual review
8. **Merchant dashboard** — shows document status, verification progress, and final approval
9. **Audit trail** — every decision is logged with the reason

## 5. MVP Scope

**In scope:**
- 3 document types: PAN card, GST certificate, Bank proof (cancelled cheque/statement)
- Synthetic/sample documents only (no real PII)
- End-to-end flow from upload to account activation
- A batch-test mode to run ~50 synthetic records and report accuracy metrics

**Explicitly minimal:**
- Auth is simple (email/password or mock OTP) — not building a full identity/security system
- Only one merchant type/flow — no multi-business-entity variations initially

## 6. User Stories

1. *As a merchant*, I want to upload my PAN card in the right slot so that I don't waste time submitting the wrong document.
2. *As a merchant*, I want to know immediately if my document is unreadable or invalid, so I can re-upload without waiting.
3. *As a merchant*, I want to see the status of my verification (in progress, approved, flagged) so I know what to expect.
4. *As a compliance reviewer*, I want to see only the flagged/exception cases with a clear reason, so I don't have to check every submission manually.
5. *As a platform owner*, I want a report showing what % of submissions were auto-approved correctly, so I can trust the automation.

## 7. Success Metrics

| Metric | Target for demo |
|---|---|
| Correct auto-approval rate | ≥ 90% on synthetic batch of 50 records |
| Correct exception-flagging rate | ≥ 90% (mismatches/invalid docs correctly caught) |
| False approval rate (bad doc approved) | 0% — highest priority, since this is the riskiest failure mode |
| Avg. time from upload to decision | < 30 seconds per merchant (excluding external DB response is mocked, so effectively instant) |
| Wrong-document-type catch rate at upload | 100% for the demo dataset |

## 8. Assumptions

- All test documents are synthetic; no real government or banking API access is used or needed.
- The 5 "external" verification sources are simulated as internal database tables seeded with test data.
- The LLM used for cross-verification (Claude) is called via API with strict, constrained prompts — it proposes findings, it does not make the final approve/reject decision.
- Judges will evaluate based on measured accuracy + audit trail quality, not on live integration with real government systems.

## 9. Risks

| Risk | Mitigation |
|---|---|
| LLM hallucinates a "match" that isn't real | LLM only outputs structured findings; a deterministic rule layer makes the final call, not the LLM directly |
| OCR misreads low-quality document images | Confidence thresholds — low-confidence extractions are auto-flagged for review, not auto-approved |
| Scope creep (trying to cover every document type/edge case) | MVP fixed to 3 document types and one merchant flow |
| Time constraint of buildathon | Feature list kept minimal; polish only what's demoed |

## 10. Out of Scope (for MVP)

- Real integration with actual government/CKYC/bank APIs
- Multi-language document support
- Video KYC
- Multi-user roles beyond merchant + reviewer
- Mobile app (web only)
- Production-grade security hardening (rate limiting, WAF, etc. — noted in architecture doc but not built for demo)

## 11. Acceptance Criteria

- [ ] A merchant can sign up, upload 3 required documents, and receive a decision without manual intervention (for clean cases)
- [ ] Uploading a wrong document type in a slot is rejected before backend processing, with a clear error message
- [ ] OCR output is converted into a structured JSON object per document
- [ ] LLM cross-verification produces a structured finding (not just free text) including a confidence score and reasoning
- [ ] At least one submission with a deliberate mismatch is correctly flagged, not approved
- [ ] A batch test of 50 synthetic records produces a report with accuracy, false-approval rate, and exception list
- [ ] Every decision (approve/reject/flag) has a logged, human-readable reason
