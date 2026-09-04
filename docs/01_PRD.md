# Product Requirements Document (PRD)
## Merchant Onboarding Copilot
**Track:** AI Risk Manager | Razorpay AI Buildathon 2026
**Version:** 2.0 (updated 2026-09-04 to the shipped system; see `session_log.md` for history)

---

## 1. Problem Statement

Merchant onboarding on payment platforms is slow and error-prone. KYC documents are reviewed by hand or checked with rigid rules. When automation is used, it is usually a black box: the merchant or the platform cannot say why an application was flagged, how risky it is compared with others, or which signals drove the outcome.

**Core problem:** there is no fast, accurate, explainable way to verify a merchant's identity documents at submission time. The system should identify risk (mismatched documents, identifiers shared across applicants), assess it (a weighted, explainable risk score), prioritize it (a review queue sorted by risk), and explain it (a full audit trail and per-check breakdown), while keeping a human in the loop for the final decision.

## 2. Target Users

| User | Description | Needs |
|---|---|---|
| Merchant (primary) | A business owner signing up to accept payments | Fast, transparent onboarding; clear errors; plain-language rejection reasons |
| Compliance or operations reviewer, and admin | Internal team handling verification | Risk-prioritized queue, full structured breakdown, one-click sign-off, confidence in the automation |
| Platform (Razorpay, in this simulation) | The business running onboarding | Measured accuracy, audit trail, defense against fraud (shared identifiers) and AI attacks (prompt injection), failure recovery |

## 3. Goals

1. Extract KYC document fields with high accuracy (vision OCR) and validate document format instantly.
2. Identify risk: cross-document inconsistencies, failures against 5 external verification sources, and identifiers shared across unrelated applications (fraud rings).
3. Assess risk: a weighted, explainable 0 to 100 score per merchant.
4. Prioritize risk: a review queue sorted by risk so the riskiest applications surface first.
5. Explain every outcome: structured per-check breakdown, immutable audit trail, and plain-language merchant messages.
6. Keep a human admin as the mandatory final decision-maker (compliance-grade human-in-the-loop).
7. Prove the system works: batch accuracy, empirical weight calibration, live failure-injection demos, and a live system-health view.

## 4. Core Features (shipped)

1. Merchant signup and login with roles (merchant, reviewer, admin).
2. Document upload with instant feedback: PAN/GST/bank-proof slots, synchronous vision-OCR extraction, and per-document states including `invalid_format` (retry) and `temporarily_unavailable` (outage).
3. LLM cross-document verification that returns strict, structured findings only, never a verdict.
4. 5-source simulated external validation plus cross-merchant fraud-ring detection.
5. Weighted, explainable risk score (0 to 100) with a per-check point breakdown.
6. Admin-triggered verification and mandatory human sign-off: `verified_matching` and `verified_mismatched` states, one-click approve, and an editable rejection cause.
7. Prompt-injection defense so hostile document text cannot corrupt the AI check.
8. Merchant dashboard with real-time status polling, plain-language reasons, and restart after rejection.
9. Append-only audit trail that logs every event with a reason and an actor.
10. Engineering showcases: batch accuracy report, risk-weight calibration, failure-injection demo, live system-health view, and Architecture Decision Records in `docs/adr/`.

## 5. Scope

**In scope:** the 3 document types; synthetic data only; the end-to-end flow of upload, verify, decide; batch accuracy over the 25 seeded ground-truth merchants; and an admin or reviewer panel with risk prioritization.

**Out of scope, by design:** real government or bank API integration (simulated on purpose); forgot-password; websockets; video KYC; multiple languages; a mobile app; payment or checkout integrations (a different buildathon track); and production-grade security hardening beyond what is listed below.

## 6. User Stories

1. As a merchant, I want to know immediately if my document is unreadable or in the wrong slot, so I can fix it without waiting.
2. As a merchant, I want to see my onboarding status live and get a plain-language reason if I am rejected, so I know exactly what to do.
3. As a reviewer, I want a risk-prioritized queue with the full per-check breakdown, so I can spend attention where it matters.
4. As an admin, I want to verify an application on demand and sign off with one click, so clean merchants activate fast and risky ones never slip through.
5. As a platform owner, I want a measured accuracy report and weight calibration, so I can trust and tune the automation.
6. As an operator, I want to see the system's health (OCR/LLM success, latencies, errors) and simulate an outage, so I can prove it fails safe.

## 7. Success Metrics (measured)

| Metric | Target | Measured (synthetic set) |
|---|---|---|
| Correct extraction of identifiers | Near 100% | 3/3 exact at confidence 0.95 (live runs) |
| Clean merchants separated from flagged by risk score | Strong separation | Clean mean 0.0 vs flagged mean 95.0 |
| Best-F1 decision cutoff | High | F1 = 1.0 at cutoff of 5 or more (25 labeled merchants) |
| False-approval rate | 0% | 0 false approvals in batch test |
| Batch-test accuracy | 90% or more | 100% on scorable records (Session 17 onward) |
| Wrong or blank document caught at upload | 100% | `invalid_format` path |
| Verification latency | Seconds | About 1.5 s per upload; about 16 s for a full verify including LLM |
| Double-processing under race | 0 | Exactly one decision and one audit entry (tested) |

## 8. Assumptions

- All test documents are synthetic. No real government or bank API access is used or needed.
- The 5 external sources are simulated as seeded database tables.
- One LLM provider (Groq, free tier) powers extraction and verification. Quota is shared, so heavy testing can temporarily exhaust it. This surfaces as a retry-friendly `temporarily_unavailable` status and resets daily.
- Judges evaluate on measured accuracy, audit-trail quality, explainability, and failure recovery, not on live integration with real government systems.

## 9. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| LLM hallucinates a match | LLM only outputs structured findings; the deterministic engine decides (ADR-001) |
| LLM or provider outage silently changes outcomes | Verification defers (503); no determination on partial signals (ADR-005) |
| Prompt injection via uploaded documents | Pre-LLM scan, redaction, forced human review (Session 21) |
| Fraud across applications | Cross-merchant shared-identifier scan |
| OCR engine unreliable | Vision-OCR swap, retries, multi-key rotation (ADR-006) |
| Double decisions or lost updates | Atomic conditional-UPDATE transitions (ADR-008) |
| Cleanup destroys evidence or hits real accounts | Soft archive only; account discriminator; Session 21b lesson (ADR-004) |
| Stale failed upload shadows a new one | `merchant-status` returns newest first (Session 21b) |

## 10. Acceptance Criteria (current system)

- [x] Merchant signs up, uploads 3 documents, gets instant per-document feedback, and reaches `submitted` with no automatic verification.
- [x] Admin verifies on demand, sees a structured matched/mismatched breakdown and risk score, and the merchant moves to `verified_matching` or `verified_mismatched`.
- [x] The admin's sign-off is the only path to `active` or `rejected`. Rejection can use the auto-drafted cause, and the merchant sees a plain-language reason.
- [x] Deliberate mismatches are flagged and never approved. Fraud-ring shared identifiers are caught.
- [x] Batch test over the 25 seeded records reports accuracy and false approvals. Risk calibration reports score separation and a cutoff sweep.
- [x] Failure toggles produce real degradation paths. Verification defers on LLM or source outage and recovers when the fault clears.
- [x] Every event has an audit-log entry with a reason. Two concurrent decisions produce exactly one.
