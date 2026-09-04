# Product Requirements Document (PRD)
## Merchant Onboarding Copilot
**Track:** AI Risk Manager | Razorpay AI Buildathon 2026
**Version:** 2.0 (updated 2026-09-04 to the shipped system — see `session_log.md` for history)

---

## 1. Problem Statement

Merchant onboarding on payment platforms is slow and error-prone because KYC documents are manually reviewed or checked with brittle rules. Worse, when automation *is* used, it is usually a black box: the merchant (or the platform) can't say *why* an application was flagged, how risky it is relative to others, or which signals drove the outcome.

**Core problem:** there is no fast, accurate, *self-explainable* way to verify a merchant's identity documents at submission time — one that identifies risk (mismatched documents, shared identifiers across applicants), assesses it (a weighted, explainable risk score), prioritizes it (a risk-sorted review queue), and explains it (a full audit trail and per-check breakdown) — while keeping a human in the loop for the final decision.

## 2. Target Users

| User | Description | Needs |
|---|---|---|
| **Merchant (primary)** | A business owner signing up to accept payments | Fast, transparent onboarding; clear errors; plain-language rejection reasons |
| **Compliance/ops reviewer + admin** | Internal team handling verification | Risk-prioritized queue, full structured breakdown, one-click sign-off, confidence in the automation |
| **Platform (Razorpay, in this simulation)** | The business running onboarding | Measured accuracy, audit trail, defense against fraud (shared identifiers) and AI attacks (prompt injection), failure recovery |

## 3. Goals

1. Automatically **extract** KYC document fields with high accuracy (vision OCR) and instantly validate document format.
2. **Identify risk**: cross-document inconsistencies, failures against 5 external verification sources, and identifiers shared across unrelated applications (fraud rings).
3. **Assess risk**: a weighted, explainable 0–100 score per merchant.
4. **Prioritize risk**: a review queue sorted by risk so the riskiest applications surface first.
5. **Explain every outcome**: structured per-check breakdown + immutable audit trail + plain-language merchant messages.
6. Keep a **human admin as the mandatory final decision-maker** (compliance-grade human-in-the-loop).
7. Prove the system works: batch accuracy, empirical weight calibration, live failure-injection demos, and a live system-health view.

## 4. Core Features (shipped)

1. **Merchant signup/login** (role-based: merchant / reviewer / admin)
2. **Document upload with instant feedback** — PAN/GST/Bank-proof slots; synchronous vision-OCR extraction; per-document states incl. `invalid_format` (retry) and `temporarily_unavailable` (outage)
3. **LLM cross-document verification** — strict, structured findings only (never a verdict)
4. **5-source simulated external validation** + **cross-merchant fraud-ring detection**
5. **Weighted explainable risk score (0–100)** with per-check point breakdown
6. **Admin-triggered verification + mandatory human sign-off** — `verified_matching` / `verified_mismatched` states, one-click approve, editable rejection cause
7. **Prompt-injection defense** — hostile document text can't corrupt the AI check
8. **Merchant dashboard** — real-time status polling, plain-language reasons, restart after rejection
9. **Audit trail** — append-only, every event logged with reason and actor
10. **Engineering showcases** — batch accuracy report, risk-weight calibration, failure-injection chaos panel, live system-health view, Architecture Decision Records (`docs/adr/`)

## 5. Scope

**In scope:** the 3 document types; synthetic data only; end-to-end upload → verify → decide; batch accuracy over the **25 seeded ground-truth merchants**; admin/reviewer panel with risk prioritization.

**Explicitly minimal / out of scope:** real government/bank API integration (simulated by design); forgot-password; websockets; video KYC; multi-language; mobile app; real payments/checkout integrations (different buildathon track); production-grade security hardening beyond what's listed.

## 6. User Stories

1. *As a merchant*, I want to know immediately if my document is unreadable or in the wrong slot, so I can fix it without waiting.
2. *As a merchant*, I want to see my onboarding status live and get a plain-language reason if I'm rejected, so I know exactly what to do.
3. *As a reviewer*, I want a risk-prioritized queue with the full per-check breakdown, so I only spend attention where it matters.
4. *As an admin*, I want to verify an application on demand and sign off with one click, so clean merchants activate fast and risky ones never slip through.
5. *As a platform owner*, I want a measured accuracy report and weight calibration, so I can trust and tune the automation.
6. *As an operator*, I want to see the system's health (OCR/LLM success, latencies, errors) and simulate an outage, so I can prove it fails safe.

## 7. Success Metrics (measured)

| Metric | Target | Measured (synthetic set) |
|---|---|---|
| Correct extraction of identifiers | ~100% | 3/3 exact @ conf 0.95 (live runs) |
| Clean merchants separated from flagged by risk score | strong separation | clean mean **0.0** vs flagged mean **95.0** |
| Best-F1 decision cutoff | high | **F1 = 1.0** at cutoff ≥ 5 (25 labeled merchants) |
| False-approval rate | 0% | **0 false approvals** in batch test |
| Batch-test accuracy | ≥ 90% | **100%** on scorable records (Session 17+) |
| Wrong/blank document caught at upload | 100% | `invalid_format` path |
| Verification latency | seconds | ~1.5 s uploads; ~16 s full verify incl. LLM |
| Double-processing under race | 0 | exactly one decision + one audit entry (tested) |

## 8. Assumptions

- All test documents are synthetic; no real government/bank API access is used or needed.
- The 5 "external" sources are simulated as seeded database tables.
- One LLM provider (Groq, free tier) powers extraction + verification; quota is shared, so heavy testing can temporarily exhaust it (surfaces as retry-friendly `temporarily_unavailable`, resets daily).
- Judges evaluate on measured accuracy, audit-trail quality, explainability, and failure recovery — not live integration with real government systems.

## 9. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LLM hallucinates a "match" | LLM only outputs structured findings; deterministic engine decides (ADR-001) |
| LLM/provider outage silently changes outcomes | Verification defers (503); no determination on partial signals (ADR-005) |
| Prompt injection via uploaded documents | Pre-LLM scan + redaction + forced human review (Session 21) |
| Fraud across applications | Cross-merchant shared-identifier scan |
| OCR engine unreliable | Vision-OCR swap; retries; multi-key rotation (ADR-006) |
| Double decisions / lost updates | Atomic conditional-UPDATE transitions (ADR-008) |
| Cleanup destroys evidence or bites real accounts | Soft archive only; account discriminator; Session 21b lesson (ADR-004) |
| Stale failed upload shadows a new one | `merchant-status` newest-first (Session 21b) |

## 10. Acceptance Criteria (current system)

- [x] Merchant signs up, uploads 3 documents, gets instant per-document feedback, reaches `submitted` with **no** automatic verification.
- [x] Admin verifies on demand → structured matched/mismatched breakdown + risk score; merchant → `verified_matching`/`verified_mismatched`.
- [x] Admin's sign-off is the only path to `active`/`rejected`; rejecting can use the auto-drafted cause; merchant sees a plain-language reason.
- [x] Deliberate mismatches are flagged, never approved; fraud-ring shared identifiers are caught.
- [x] Batch test over the 25 seeded records reports accuracy + false approvals; risk calibration reports score separation + cutoff sweep.
- [x] Chaos toggles produce real degradation paths; deferral on LLM/source outage; recovery on clear.
- [x] Every event has an audit-log entry with a reason; two concurrent decisions produce exactly one.
