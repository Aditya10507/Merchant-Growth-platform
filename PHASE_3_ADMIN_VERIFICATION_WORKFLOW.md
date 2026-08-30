# PHASE_3_ADMIN_VERIFICATION_WORKFLOW.md

**Read this file in full before writing any code.** Also read `KNOWLEDGE.md`, `AGENT_INSTRUCTIONS.md`, and `session_log.md`'s most recent entries first — this document extends all of them and does not override any non-negotiable rule already established (LLM never decides, no real PII, flat folder structure, etc.), except where explicitly noted in Section 3 below.

---

## 1. Current system workflow (as of the last session)

1. Merchant signs up, uploads PAN / GST / Bank proof documents.
2. Each document gets an **instant, per-document format check** (OCR + regex pattern match) on upload — "Valid document" or "Invalid document." This part is correct and unchanged by this phase.
3. Once all 3 documents pass their format check, `documents.py`'s `_run_verification_if_ready()` **automatically** runs, in the background, with no admin involved:
   - LLM cross-document consistency check (`verify.cross_verify_documents`)
   - The 5 simulated external verification sources, checked **in sequence with short-circuiting** — `decision.py`'s `check_external_sources()` returns on the **first** failure it finds and never checks the remaining sources
   - The result is logged as a single `system_recommendation` audit entry (a technical, prose reason) and the merchant's `onboarding_status` becomes `"submitted"`.
4. Admin panel's "Submitted" tab shows these merchants. Opening one shows the single system-recommendation text (buried in the audit trail) plus **two buttons that are always available regardless of what the recommendation said**: Approve or Reject, each requiring the admin to **type a free-text note by hand**.
5. Admin's click is the only thing that sets `onboarding_status` to `"active"` or `"rejected"` — this part (mandatory human sign-off) is correct and unchanged by this phase.
6. **Known bug:** once a merchant is approved, `DashboardPage.tsx` shows the "activated" success banner correctly, but never hides the document upload slots — the merchant still sees three "Click to upload" boxes with no reason to interact with them.

---

## 2. Current internal architecture (relevant parts only)

**Database (`backend/db.py`):**
- `Merchant`: `id, business_name, email, password_hash, role, onboarding_status, rejection_reason, created_at`. `rejection_reason` is only ever populated by an admin's reject decision (via `verify.humanize_reason`), never before.
- `Document`: `id, merchant_id, doc_type, file_path, extracted_fields_json, ocr_confidence, verification_status, rejection_reason, is_active, created_at, updated_at`.
- `AuditLog`: `id, merchant_id, document_id, action, reason, created_at` — free-text `reason`, not structured data. This is currently the *only* place the automated check's findings are stored.
- The 5 simulated external tables: `govt_database` (keyed by `pan_number`), `ckyc_records` (keyed by `pan_number`), `automated_verification` (keyed by `pan_number`), `bank_account_validation` (keyed by `account_number`, no merchant link column), `compliance_reviews` (keyed by `pan_number`).

**Backend logic:**
- `decision.py`'s `check_external_sources(db, pan_number, account_number)` returns a single `DecisionOutcome(decision, reason)` — one decision, one reason string, and **it stops checking as soon as it finds one problem**. It never reports "PAN failed AND bank failed" — only whichever it happened to check first.
- `documents.py`'s `_run_verification_if_ready()` calls this automatically once all 3 documents are format-valid, and only ever writes the result to the audit log — it doesn't persist structured matched/mismatched data anywhere queryable.
- `admin.py`'s `decide_application(merchant_id, {decision, note})` requires `onboarding_status == "submitted"` and requires the admin to supply `note` (min 3 characters) by hand every time, for every merchant, whether approving or rejecting.

**Frontend:**
- `DashboardPage.tsx` hides document slots only for `"rejected"` and `"submitted"` — not for `"active"` (this is bug #1 above).
- `AdminPage.tsx`'s single decision form (Approve/Reject + free-text note) appears identically for every `"submitted"` merchant, regardless of what the background check found.

---

## 3. What we're changing

| # | Change | Why |
|---|---|---|
| 1 | Fix: hide document slots once `onboarding_status === "active"`, not just `rejected`/`submitted` | Bug — merchant sees a pointless upload UI after activation |
| 2 | Remove the *automatic* trigger of the LLM+external-check pipeline from the upload flow. Add a new **admin-triggered** `POST /admin/merchants/{id}/verify` endpoint that runs it on demand | The admin should decide *when* to check, not have it happen invisibly the moment the 3rd document lands |
| 3 | Rework `decision.py` to **evaluate every check, not just the first one that fails**, and return a structured breakdown (which checks matched, which mismatched, and which document each relates to) instead of one aggregate reason string | Needed so "read all the details" and "which document mismatched" are both possible — the current short-circuit design can only ever report one problem at a time |
| 4 | Persist that structured breakdown on the `Merchant` row: `matched_checks`, `mismatched_checks` (JSON columns), and a derived `rejection_cause` (plain text, auto-generated from the mismatched checks) | "Store both the matching and mismatched data in separate columns," per your request |
| 5 | New intermediate merchant states: `"verified_matching"` and `"verified_mismatched"`, entered after the admin runs verification, before the final decision | Lets the admin panel show two clearly separated buckets, exactly as you described |
| 6 | `decide_application` no longer *requires* a hand-typed note. Approving is one click. Rejecting defaults to the stored `rejection_cause` (admin can still edit it before sending, but doesn't have to write one from scratch) | "The admin can send the rejection message with one click" |
| 7 | Each rejected merchant gets **their own specific** `rejection_reason`, derived from *their own* `mismatched_checks`, not a shared generic message | Two merchants failing for different reasons (PAN mismatch vs. bank mismatch) must see different messages |

**Everything else stays as-is:** the LLM still only ever proposes findings, never decides (Rule 1 in `KNOWLEDGE.md` still holds — if anything it's reinforced, since now there's no automatic pathway to a decision at all). The 5 external tables remain simulated. No new document types. No change to auth, restart-application, or the instant format check.

---

## 4. Where to work

### Backend

| File | What changes |
|---|---|
| `db.py` | Add to `Merchant`: `matched_checks` (Text, nullable — JSON string), `mismatched_checks` (Text, nullable — JSON string), `rejection_cause` (Text, nullable). Keep existing `rejection_reason` as the *final, sent* message (unchanged meaning); `rejection_cause` is the *pre-decision, admin-facing* draft derived from `mismatched_checks`. |
| `schema.sql` | Regenerate after the `db.py` change. |
| `schemas.py` | Add `VerificationStatus` values `"verified_matching"`, `"verified_mismatched"` (merchant-level; can reuse the same `onboarding_status: str` field, no schema change needed there since it's untyped). Add `CheckResult` (`check_name: str, document_type: str, matched: bool, detail: str`) and `VerificationBreakdown` (`matched: list[CheckResult], mismatched: list[CheckResult], rejection_cause: str \| None`) response/internal models. Make `ResolveExceptionRequest.note` optional (`note: Optional[str] = None`). |
| `decision.py` | Rewrite `check_external_sources()` to check **all 5 sources unconditionally** (no early return) and return a `VerificationBreakdown` instead of a single `DecisionOutcome`. Map each source to a `document_type`: `govt_database`/`ckyc_records`/`automated_verification`/`compliance_reviews` → `"PAN"`; `bank_account_validation` → `"BANK_PROOF"`. Also fold in the LLM's per-field findings (from `verify.cross_verify_documents`) as additional `CheckResult` entries — a `consistent=False` finding becomes a mismatched entry too. Keep `evaluate()` for the OCR-confidence-too-low instant-rejection path (unchanged, still per-document at upload time, unrelated to this admin-triggered step). |
| `verify.py` | Add `generate_rejection_cause(mismatched: list[CheckResult]) -> str`: joins the mismatched checks into one clear, humanized, multi-part message via the existing `humanize_reason`-style strict prompt (rephrase only, cite each mismatched document by name, never invent). If `mismatched` is empty, this function isn't called. |
| `documents.py` | In `_run_verification_if_ready()`, **remove** the LLM/external-check call entirely. It now only checks "are all 3 documents format-valid" and sets `onboarding_status = "submitted"` — nothing more. |
| `admin.py` | Add `POST /admin/merchants/{id}/verify`: precondition `onboarding_status == "submitted"`; runs the LLM cross-check + `decision.check_external_sources()` (now returning a `VerificationBreakdown`), stores `matched_checks`/`mismatched_checks` as JSON on the `Merchant` row, computes `rejection_cause` via `verify.generate_rejection_cause()` if there are mismatches, and sets `onboarding_status` to `"verified_matching"` or `"verified_mismatched"`. Update `decide_application`: precondition becomes `onboarding_status in ("verified_matching", "verified_mismatched")`; if rejecting and no `note` is supplied, use the stored `rejection_cause` as the humanized reason instead of requiring one; if a `note` *is* supplied, prefer it (admin override). Add the breakdown (`matched_checks`, `mismatched_checks`, `rejection_cause`) to `MerchantDetailResponse` so the admin panel can render it. |

### Frontend

| File | What changes |
|---|---|
| `types.ts` | Add `CheckResult`, `VerificationBreakdown` types (mirroring the backend schemas exactly). Add `matched_checks`, `mismatched_checks`, `rejection_cause` to `MerchantDetail`. Make `note` optional in the `decideApplication` call signature. |
| `constants.ts` | Add labels for `"verified_matching"` ("Verified — matches") and `"verified_mismatched"` ("Verified — mismatch found") to `STATUS_LABELS`, plus a style entry in `StatusBadge.tsx`. |
| `api.ts` | Add `verifyApplication(merchantId): Promise<MerchantDetail>` calling the new endpoint. Update `decideApplication` to accept an optional `note`. |
| `pages/DashboardPage.tsx` | Fix bug #1: hide the document slot grid when `onboarding_status === "active"` too (not just `rejected`/`submitted`) — show only the success banner. |
| `pages/AdminPage.tsx` | Replace the single always-shown Approve/Reject form with a state-dependent view: **`"submitted"`** → show one button, "Verify with internal databases," calling `verifyApplication`. **`"verified_matching"`** → show the matched-checks list and a single "Approve & activate" button (no note needed). **`"verified_mismatched"`** → show the mismatched-checks list, the stored `rejection_cause` in an editable textarea (pre-filled, admin can adjust before sending), and a single "Reject & notify" button. Add `"verified_matching"`/`"verified_mismatched"` to the status filter tabs (can combine into one "Verified" tab with the two groups shown separately, or two tabs — your coding agent's call, keep it simple). |
| `components/VerificationTimeline.tsx` | No structural change needed — the `system_recommendation` audit action goes away (replaced by the richer stored breakdown), but keep the timeline rendering whatever audit actions still get logged (e.g., log a new `"verification_run"` action when the admin triggers verify, and keep `"manual_review_resolution"` for the final decision). |

---

## 5. Final architecture & data flow

**Merchant status state machine:**

```
pending
   │ (all 3 docs uploaded + pass instant format check)
   ▼
submitted
   │ (admin clicks "Verify with internal databases")
   ▼
verified_matching  ──────────────┐         verified_mismatched
   │ (admin clicks "Approve")    │            │ (admin clicks "Reject", using
   ▼                             │            │  the stored/edited rejection_cause)
active                           │            ▼
                                 │         rejected
                                 │            │ (merchant clicks "Start new application")
                                 └────────────▼
                                          pending (restart, existing flow, unchanged)
```

**Data flow for one merchant, mismatched case:**

1. Merchant uploads PAN, GST, Bank proof → each passes instant format check → `onboarding_status = "submitted"`.
2. Admin opens the merchant in the panel, clicks **"Verify with internal databases."**
3. Backend runs, in one request:
   - `verify.cross_verify_documents()` → LLM findings (per-field consistent/inconsistent)
   - `decision.check_external_sources()` → checks **all 5** sources, e.g.: govt_database ✅ matched, ckyc_records ✅ matched, automated_verification ❌ mismatched ("identity check failed"), bank_account_validation ❌ mismatched ("account could not be validated"), compliance_reviews ✅ matched
4. Backend assembles: `matched_checks = [govt_database, ckyc_records, compliance_reviews, ...any consistent LLM findings]`, `mismatched_checks = [{document_type: "PAN", check_name: "automated_verification", detail: "identity check failed"}, {document_type: "BANK_PROOF", check_name: "bank_account_validation", detail: "account could not be validated"}]`.
5. `verify.generate_rejection_cause()` turns that into one clear sentence, e.g.: *"We couldn't verify your PAN details or your bank account information. Please double-check both and resubmit."*
6. These are stored on the `Merchant` row (`matched_checks`, `mismatched_checks`, `rejection_cause` — all populated). `onboarding_status = "verified_mismatched"`.
7. Admin panel now shows this merchant under the mismatched bucket, with the exact two failed checks listed and the drafted rejection message ready to review.
8. Admin clicks **"Reject & notify"** (editing the message first, if they want). `decide_application` sets `onboarding_status = "rejected"`, `rejection_reason = <the reviewed message>` (humanized if edited, or the stored cause if not), and logs the final audit entry.
9. Merchant's dashboard polls, sees `"rejected"` with **that specific** message — not a generic one, and not the same message another merchant with a different problem would see.

**Matching case is the same flow through step 4-6** but `mismatched_checks` is empty, `rejection_cause` stays null, `onboarding_status = "verified_matching"`, and the admin's one click is "Approve & activate" instead.

---

## 6. Coding instructions (same standards as the rest of the project — repeated here for this phase)

- Strict TypeScript, no `any`; every new backend function has type hints on params and return type.
- `matched_checks`/`mismatched_checks` are stored as JSON strings in Text columns (SQLite has no native JSON type here) — always `json.dumps`/`json.loads` at the boundary, never pass raw dicts to SQLAlchemy. Mirror the existing pattern used for `Document.extracted_fields_json`.
- `decision.check_external_sources()` must **never** raise on a missing record — a missing PAN/CKYC/bank row is itself a mismatch to report (`matched=False, detail="not found"`), not an exception. Keep this consistent with the existing "external check failures are data, not errors" pattern.
- `verify.generate_rejection_cause()` follows the exact same anti-hallucination rules as `humanize_reason()`: rephrase only, cite only what's in the `mismatched_checks` list, never invent a reason not present in the input, never mention internal system/table names.
- Every new admin endpoint stays role-gated via `require_role("reviewer", "admin")`, validates its precondition (correct `onboarding_status`) with a 409 on mismatch, exactly like `decide_application` already does.
- Every new frontend state (matched-checks list, mismatched-checks list, verify button, decide buttons) follows the existing `AsyncState<T>` loading/success/error pattern — no new ad-hoc boolean flags.
- No hardcoded strings for status values — add any new ones to `constants.ts`'s `STATUS_LABELS`/`STATUS_STYLES` and the backend's `Literal` types, never inline a string comparison against a status your coding agent invented on the spot.
- Comment blocks at the top of every rewritten function explaining the *why* (especially the "check everything, don't short-circuit" change in `decision.py` — that's a deliberate behavior change from the existing code, worth flagging clearly so a future reader doesn't "fix" it back).
- After implementation, update `KNOWLEDGE.md`'s non-negotiable rules (the current ones describe a single-outcome, short-circuiting check — that needs rewriting) and append a `session_log.md` entry, exactly as done in the previous two sessions — this is now an established project convention, keep it going.

## Phase-wise plan

**Phase 1 — Quick fix (do this first, independent of everything else)**
- Fix `DashboardPage.tsx` to hide document slots when `onboarding_status === "active"`.
- Test: sign up, get approved (via existing flow), confirm the upload boxes disappear and only the success banner shows.

**Phase 2 — Backend: structured, non-short-circuiting verification**
- Rewrite `decision.check_external_sources()` to check all 5 sources and return a `VerificationBreakdown`.
- Add the new `Merchant` columns, regenerate `schema.sql`.
- Add `verify.generate_rejection_cause()`.
- Test: call the rewritten function directly (unit-test style, mocking the DB rows) with a merchant that fails 2 of 5 checks — confirm both failures are reported, not just the first.

**Phase 3 — Backend: admin-triggered verify + reworked decide**
- Remove the automatic call from `documents.py`'s `_run_verification_if_ready()`.
- Add `POST /admin/merchants/{id}/verify`.
- Update `decide_application`'s precondition and optional-note/stored-cause logic.
- Test end-to-end via `TestClient` (mocking OCR/LLM as done in previous sessions): upload 3 docs → confirm status is `"submitted"` and stays there (no auto-verification) → call verify → confirm status becomes `verified_matching` or `verified_mismatched` with the right data → call decide → confirm final state and that the merchant-visible reason matches the stored `rejection_cause` for a mismatched case.

**Phase 4 — Frontend**
- Update `types.ts`, `constants.ts`, `api.ts`.
- Rework `AdminPage.tsx`'s detail view into the three-state UI (submitted → verify button; verified_matching → approve button; verified_mismatched → editable cause + reject button).
- Test: `npx tsc -b --noEmit` (zero errors), `npm run build`, then a manual click-through of all three states.

**Phase 5 — Docs**
- Update `KNOWLEDGE.md` non-negotiable rules 1–2 to describe the new admin-triggered, non-short-circuiting flow.
- Append a `session_log.md` entry summarizing the change, same convention as before.
- Update `docs/01_PRD.md`'s success metrics section if it still describes full automation (flagged as outstanding in the last session's log — good time to finally address it).
