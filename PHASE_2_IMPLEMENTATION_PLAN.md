# PHASE_2_IMPLEMENTATION_PLAN.md

**Read this file in full before writing any code.** Also read `KNOWLEDGE.md` (project context) and `AGENT_INSTRUCTIONS.md` (coding standards) first — this document is additive to both and does not override any non-negotiable rule already listed there (LLM never makes the final decision, external verification tables stay simulated, flat folder structure, no forgot-password flow, etc.).

This document specifies **exactly** what to build, with concrete code snippets where precision matters (schema fields, function signatures, status enums), so there is no ambiguity or drift from the existing codebase's patterns.

---

## 0. What's being added in this phase (5 features)

1. **Instant document validity feedback** — merchant sees "Valid document" / "Invalid document" immediately after upload, before deeper verification runs.
2. **Restart-application-from-scratch** — a rejected merchant can start a completely new application; old documents are preserved for audit but retired.
3. **LLM-humanized rejection reasons** — the Decision Engine's technical reason gets rephrased into a plain-language, actionable message for the merchant (LLM only rephrases, never decides or invents).
4. **Admin/Reviewer panel** — a screen for the `reviewer`/`admin` role to see all merchants (filterable by status), drill into full verification detail, and manually resolve `flagged` cases.
5. **Verification timeline component** — a shared, reusable audit-trail visualization used in both the admin detail view and (in a reduced form) the merchant's own dashboard.

---

## 1. Design principles specific to this phase

- **Pattern matching, not exact matching.** The document-type validity check (already implemented as `_TYPE_SIGNATURES` in `backend/documents.py`) matches extracted text against a *format* (e.g., "does this look like a PAN number: 5 letters + 4 digits + 1 letter?"), never against one specific sample document's literal values. Do not build anything that compares extracted data to a fixed example's exact values — that would reject every real, valid document except one.
- **The LLM only ever rephrases a reason that already exists.** `humanize_reason()` (Feature 3) must never generate a new reason, add information not present in the input, or imply an approval/rejection decision. This is the same safety principle already enforced in `verify.py`'s cross-verification step — extend it, don't weaken it.
- **Restart soft-retires documents, never deletes them.** Old documents get `is_active = False`, preserved in the database for the audit trail and admin panel. This matters for compliance-style auditability — the PRD's audit trail requirement applies across the merchant's full history, not just their current attempt.
- **Reviewers only act on `flagged` merchants.** The admin panel must never allow overriding an already-`active` (approved) or already-`rejected` merchant. This preserves the core pitch ("no human needed for the clean path") and keeps scope bounded.

---

## 2. Feature 1: Instant document validity feedback

**Current state (already built, do not rebuild):** `upload_document()` in `backend/documents.py` already runs OCR, then checks the result against `_TYPE_SIGNATURES` immediately after. On a mismatch it already short-circuits before any LLM/external check runs.

**Changes required:**

### 2.1 — Add a new status value

In `backend/schemas.py`, extend the `VerificationStatus` literal:

```python
VerificationStatus = Literal["uploaded", "verifying", "invalid_format", "approved", "flagged", "rejected"]
```

`invalid_format` is distinct from `rejected`: it means "wrong kind of document uploaded, just try again in this same slot" — a fast, cheap fix. `rejected` is reserved for the final Decision Engine outcome after full verification, which requires restarting the whole application (Feature 2).

### 2.2 — Update the type-mismatch branch

In `backend/documents.py`, inside `upload_document()`, change the existing type-signature-mismatch branch:

```python
signature = _TYPE_SIGNATURES.get(doc_type)
joined_text = " ".join(fields.values())
if signature and not signature.search(joined_text):
    reason = f"Uploaded file does not appear to be a valid {doc_type.replace('_', ' ').title()} document"
    document.verification_status = "invalid_format"   # was "rejected"
    document.rejection_reason = reason
    db.commit()
    decision.log_decision(db, merchant.id, document.id, decision.DecisionOutcome(decision.Decision.REJECTED, reason))
    return _to_response(document)
```

(Note: still log the audit entry as a `REJECTED`-type outcome for audit-trail consistency — only the *document's* displayed status changes, not the audit action taxonomy.)

### 2.3 — Frontend: status badge

In `frontend/src/components/StatusBadge.tsx`, add a style + label for `invalid_format`:

```typescript
invalid_format: "bg-red-100 text-red-800",
```
```typescript
invalid_format: "Invalid document",
```
(Add to both `STATUS_STYLES` and `constants.ts`'s `STATUS_LABELS`.)

### 2.4 — Frontend: DocumentSlot messaging

In `frontend/src/components/DocumentSlot.tsx`:
- On receiving `verification_status === "invalid_format"` in the upload response, show a clear `Alert variant="error"`: *"Invalid document — please check the document and try again."* The file input should remain enabled immediately (it already is, since only `"verifying"` disables it — no change needed there).
- On receiving any other non-`invalid_format` status back from a successful upload (i.e. it passed the format check and is now `"verifying"`), show a brief, dismissable `Alert variant="success"`: *"Valid document — verifying identity details..."* This is inferred purely from the status transition; no new backend field is needed for the "valid" case.

Do not add a separate persisted "valid, still checking" database status — that would over-complicate the state machine for no real benefit. The single `"verifying"` status already covers that window; only the fast format-check failure needs its own distinct status because it must feel instant and be fixable without restarting anything.

---

## 3. Feature 2: Restart application from scratch

### 3.1 — Database schema changes

In `backend/db.py`, import `Boolean` from `sqlalchemy` (add to the existing import line), then:

**On `Merchant`:**
```python
# Merchant-facing, plain-language explanation shown on the dashboard
# when onboarding_status is "rejected" or "flagged". Always derived
# from decision.py's technical reason via verify.humanize_reason() —
# never an LLM-invented reason, only a rephrasing of one.
rejection_reason = Column(Text, nullable=True)
```

**On `Document`:**
```python
# False once a merchant restarts their application after a rejection.
# Kept (not deleted) so the audit trail/admin panel retains full
# history; only active documents count toward the merchant's current
# application and appear on their dashboard.
is_active = Column(Boolean, nullable=False, default=True)
```

**After this change:** regenerate `backend/schema.sql` (see the generation snippet already documented in that file's header comment, or re-run the `CreateTable`/`CreateIndex` compilation used to generate it originally).

### 3.2 — Query changes (critical — easy to miss one)

Every query that represents "the merchant's current application" must filter `Document.is_active == True`. This applies to:
- `get_merchant_status()` in `documents.py`
- `_run_verification_if_ready()`'s check for "are all 3 document types present"
- `get_document_status()` — a merchant should not be able to fetch a retired document via its old ID either; filter this one too, or explicitly 404 if `is_active` is False.
- `admin.py`'s `list_exceptions()` and the new merchant-detail endpoint (Feature 4) — the admin panel should only show *active* documents for "current status," even though old ones remain queryable via the full audit log.

### 3.3 — New endpoint: restart application

Add to `backend/documents.py`:

```python
@router.post("/restart-application", response_model=MerchantStatusResponse)
def restart_application(
    merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
) -> MerchantStatusResponse:
    if merchant.onboarding_status != "rejected":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a rejected application can be restarted",
        )

    active_docs = db.query(Document).filter(Document.merchant_id == merchant.id, Document.is_active == True).all()
    for doc in active_docs:
        doc.is_active = False

    merchant.onboarding_status = "pending"
    merchant.rejection_reason = None
    db.add(AuditLog(merchant_id=merchant.id, action="application_restarted", reason="Merchant started a new application after rejection"))
    db.commit()

    return MerchantStatusResponse(merchant_id=merchant.id, onboarding_status=merchant.onboarding_status, rejection_reason=None, documents=[])
```

(Import `AuditLog` in `documents.py` if not already imported.)

### 3.4 — Block uploads into a rejected application

At the top of `upload_document()` in `documents.py`, add a precondition check:

```python
if merchant.onboarding_status == "rejected":
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="This application was rejected. Please start a new application before uploading documents.",
    )
```

### 3.5 — Frontend

- `frontend/src/api.ts`: add
  ```typescript
  export function restartApplication(): Promise<MerchantStatus> {
    return request<MerchantStatus>("/documents/restart-application", { method: "POST" });
  }
  ```
- `frontend/src/pages/DashboardPage.tsx`: when `statusState.data.onboarding_status === "rejected"`, hide the document slot grid entirely, show `statusState.data.rejection_reason` in an `Alert variant="error"`, and show a `Button` labeled "Start a new application" that calls `restartApplication()`, then re-triggers `fetchStatus()` so the (now-empty) slots reappear.

---

## 4. Feature 3: LLM-humanized rejection reasons

### 4.1 — New function in `backend/verify.py`

```python
_HUMANIZE_SYSTEM_PROMPT = """You rephrase an internal verification system's \
technical rejection/flag reason into one or two short, plain-language \
sentences for a small business owner with no technical background.

STRICT RULES:
1. Only rephrase what is given. Never add a fact, number, or explanation \
   that isn't already present in the input.
2. Never mention internal system details: no OCR, no "LLM", no AI model \
   names, no database/table names, no confidence scores as raw numbers.
3. If the input implies a corrective action (e.g. re-upload a clearer \
   image), state that action plainly. If it doesn't, don't invent one.
4. Respond with ONLY the rephrased message. No preamble, no quotes, no \
   markdown.
"""

def humanize_reason(technical_reason: str) -> str:
    try:
        response = _get_client().messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=200,
            system=_HUMANIZE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": technical_reason}],
        )
        text_blocks = [b.text for b in response.content if b.type == "text"]
        humanized = "\n".join(text_blocks).strip()
        return humanized or technical_reason
    except Exception:
        # Humanizing is a nice-to-have, never a blocker. On any failure,
        # fall back to the original technical reason rather than
        # crashing the request or leaving the merchant with nothing.
        logger.warning("humanize_reason failed, falling back to technical reason", exc_info=True)
        return technical_reason
```
(Add `import logging; logger = logging.getLogger(__name__)` near the top of `verify.py` if not already present.)

### 4.2 — Wire it into the decision flow

In `documents.py`'s `_run_verification_if_ready()`, after computing `outcome`:

```python
if outcome.decision in (decision.Decision.FLAGGED, decision.Decision.REJECTED):
    merchant.rejection_reason = verify.humanize_reason(outcome.reason)
else:
    merchant.rejection_reason = None
```

Keep `document.rejection_reason` (per-document) as the raw technical reason for the admin panel/audit trail — only `merchant.rejection_reason` is the humanized, merchant-facing version.

### 4.3 — Frontend

`MerchantStatus` in `types.ts` and `MerchantStatusResponse` in `schemas.py` both already include `rejection_reason: string | null` (see Feature 2's response shape) — `DashboardPage.tsx` renders this field directly, no further mapping needed.

---

## 5. Feature 4: Admin/Reviewer panel

### 5.1 — New Pydantic schemas (add to `backend/schemas.py` exactly as below)

```python
class MerchantSummaryResponse(BaseModel):
    merchant_id: int
    business_name: str
    email: str
    onboarding_status: str
    created_at: str


class AuditLogEntryResponse(BaseModel):
    action: str
    reason: str
    document_id: Optional[int] = None
    created_at: str


class MerchantDetailResponse(BaseModel):
    merchant_id: int
    business_name: str
    email: str
    onboarding_status: str
    rejection_reason: Optional[str] = None
    documents: list[DocumentStatusResponse]
    audit_trail: list[AuditLogEntryResponse]


class ResolveExceptionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(min_length=3, max_length=1000)
```

### 5.2 — New endpoints in `backend/admin.py`

```python
@router.get("/merchants", response_model=list[MerchantSummaryResponse])
def list_merchants(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    _reviewer: Merchant = Depends(require_role("reviewer", "admin")),
) -> list[MerchantSummaryResponse]:
    query = db.query(Merchant).filter(Merchant.role == "merchant")
    if status_filter:
        query = query.filter(Merchant.onboarding_status == status_filter)
    return [
        MerchantSummaryResponse(
            merchant_id=m.id, business_name=m.business_name, email=m.email,
            onboarding_status=m.onboarding_status, created_at=m.created_at.isoformat(),
        )
        for m in query.all()
    ]


@router.get("/merchants/{merchant_id}", response_model=MerchantDetailResponse)
def get_merchant_detail(
    merchant_id: int,
    db: Session = Depends(get_db),
    _reviewer: Merchant = Depends(require_role("reviewer", "admin")),
) -> MerchantDetailResponse:
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")

    active_docs = db.query(Document).filter(Document.merchant_id == merchant_id, Document.is_active == True).all()
    audit_entries = db.query(AuditLog).filter(AuditLog.merchant_id == merchant_id).order_by(AuditLog.created_at.asc()).all()

    return MerchantDetailResponse(
        merchant_id=merchant.id, business_name=merchant.business_name, email=merchant.email,
        onboarding_status=merchant.onboarding_status, rejection_reason=merchant.rejection_reason,
        documents=[documents_module._to_response(d) for d in active_docs],  # reuse existing mapper, see note below
        audit_trail=[
            AuditLogEntryResponse(action=a.action, reason=a.reason, document_id=a.document_id, created_at=a.created_at.isoformat())
            for a in audit_entries
        ],
    )


@router.post("/exceptions/{merchant_id}/resolve", response_model=MerchantSummaryResponse)
def resolve_exception(
    merchant_id: int,
    payload: ResolveExceptionRequest,
    db: Session = Depends(get_db),
    reviewer: Merchant = Depends(require_role("reviewer", "admin")),
) -> MerchantSummaryResponse:
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if merchant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")
    if merchant.onboarding_status != "flagged":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only flagged merchants can be resolved")

    merchant.onboarding_status = "active" if payload.decision == "approved" else "rejected"
    if payload.decision == "rejected":
        merchant.rejection_reason = verify.humanize_reason(payload.note)
    else:
        merchant.rejection_reason = None

    db.add(AuditLog(
        merchant_id=merchant.id, action="manual_review_resolution",
        reason=f"Reviewer decision: {payload.decision} — {payload.note} (by {reviewer.email})",
    ))
    db.commit()

    return MerchantSummaryResponse(
        merchant_id=merchant.id, business_name=merchant.business_name, email=merchant.email,
        onboarding_status=merchant.onboarding_status, created_at=merchant.created_at.isoformat(),
    )
```

**Note:** `admin.py` will need `import documents as documents_module` (or restructure `_to_response` into a shared location, e.g. move it to `schemas.py` as a plain function or a small `mappers.py` if it's needed in two files — pick whichever keeps `documents.py` and `admin.py` decoupled without duplicating the mapping logic; do not copy-paste the function body). Also import `verify`, `AuditLog`, `Document`, `Optional` as needed.

### 5.3 — Frontend

**`frontend/src/types.ts`** — add, mirroring the backend schemas field-for-field:
```typescript
export interface MerchantSummary {
  merchant_id: number;
  business_name: string;
  email: string;
  onboarding_status: string;
  created_at: string;
}

export interface AuditLogEntry {
  action: string;
  reason: string;
  document_id: number | null;
  created_at: string;
}

export interface MerchantDetail {
  merchant_id: number;
  business_name: string;
  email: string;
  onboarding_status: string;
  rejection_reason: string | null;
  documents: DocumentStatus[];
  audit_trail: AuditLogEntry[];
}
```

**`frontend/src/api.ts`** — add:
```typescript
export function getAdminMerchants(statusFilter?: string): Promise<MerchantSummary[]> {
  const query = statusFilter ? `?status_filter=${statusFilter}` : "";
  return request<MerchantSummary[]>(`/admin/merchants${query}`);
}

export function getMerchantDetail(merchantId: number): Promise<MerchantDetail> {
  return request<MerchantDetail>(`/admin/merchants/${merchantId}`);
}

export function resolveException(
  merchantId: number,
  decision: "approved" | "rejected",
  note: string
): Promise<MerchantSummary> {
  return request<MerchantSummary>(`/admin/exceptions/${merchantId}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, note }),
  });
}
```

**New page `frontend/src/pages/AdminPage.tsx`:**
- Status filter tabs (All / Pending / Flagged / Approved / Rejected) — reuse `Button` for tab styling (active/inactive variant), fetch via `getAdminMerchants(statusFilter)`.
- A list of `MerchantSummary` rows; clicking one loads `getMerchantDetail(id)` into a detail panel (a side panel or modal — your choice, keep it a single reusable pattern).
- Detail panel shows: merchant info, each document's extracted fields + OCR confidence + status (reuse `StatusBadge`), and the `VerificationTimeline` (Feature 5) fed by `audit_trail`.
- If `onboarding_status === "flagged"`, show a resolve form: a text area for `note` (required, min 3 chars — mirror backend validation client-side too) and two buttons, "Approve" and "Reject," calling `resolveException`. On success, refresh both the detail panel and the list.
- Follow the existing `AsyncState<T>` pattern from `types.ts` for all three fetches (list, detail, resolve-submission) — loading/success/error states must all be visibly handled, per `AGENT_INSTRUCTIONS.md` section 4.

**`frontend/src/App.tsx`** — route by role:
```typescript
function AppContent() {
  const { session } = useAuth();
  if (!session) return <AuthPage />;
  if (session.role === "reviewer" || session.role === "admin") return <AdminPage />;
  return <DashboardPage />;
}
```

---

## 6. Feature 5: Verification timeline component

**New component `frontend/src/components/VerificationTimeline.tsx`:**
- Props: `{ entries: AuditLogEntry[] }`.
- Renders a vertical list, one row per entry, each showing: a small dot/icon, the `action` as a short label (map known action strings — `"approved"`, `"flagged"`, `"rejected"`, `"application_restarted"`, `"manual_review_resolution"` — to human-readable labels via a `Record<string, string>` constant, similar to `STATUS_LABELS` in `constants.ts`), the `reason` text, and a formatted `created_at` timestamp.
- Memoize with `memo()`, matching every other component in `frontend/src/components/`.
- **Used in two places:**
  1. `AdminPage.tsx`'s merchant detail view — show the full, raw technical `reason` text (this audience needs the real detail).
  2. Optionally, `DashboardPage.tsx` for the merchant's own view — if included, do not show raw technical reasons here; only show the `action` labels and timestamps (a simple progress trail), since the merchant-facing explanation already lives in `rejection_reason` (Feature 3). Do not leak internal technical detail to the merchant view.

---

## 7. File-by-file change list

### Backend

| File | Change |
|---|---|
| `db.py` | Add `Boolean` import; add `Merchant.rejection_reason`; add `Document.is_active` |
| `schema.sql` | Regenerate after `db.py` changes |
| `schemas.py` | Extend `VerificationStatus` literal; add `rejection_reason` to `MerchantStatusResponse`; add `MerchantSummaryResponse`, `AuditLogEntryResponse`, `MerchantDetailResponse`, `ResolveExceptionRequest` |
| `verify.py` | Add `humanize_reason()` + its system prompt; add logging import |
| `documents.py` | Update type-mismatch branch to use `"invalid_format"`; filter all "current application" queries by `Document.is_active == True`; add `restart_application` endpoint; block uploads when `onboarding_status == "rejected"`; call `humanize_reason` in `_run_verification_if_ready` |
| `admin.py` | Add `list_merchants`, `get_merchant_detail`, `resolve_exception` endpoints |

### Frontend

| File | Change |
|---|---|
| `types.ts` | Extend `VerificationStatus`; add `rejection_reason` to `MerchantStatus`; add `MerchantSummary`, `AuditLogEntry`, `MerchantDetail` |
| `constants.ts` | Add `invalid_format` to `STATUS_LABELS`; add action-label map for the timeline |
| `api.ts` | Add `restartApplication`, `getAdminMerchants`, `getMerchantDetail`, `resolveException` |
| `components/StatusBadge.tsx` | Add `invalid_format` style |
| `components/DocumentSlot.tsx` | Add valid/invalid instant messaging |
| `components/VerificationTimeline.tsx` | New component |
| `pages/DashboardPage.tsx` | Handle `rejected` state (hide slots, show reason, restart button) |
| `pages/AdminPage.tsx` | New page |
| `App.tsx` | Route by role |

---

## 8. New/changed API contract summary

| Endpoint | Method | Auth | Notes |
|---|---|---|---|
| `/documents/restart-application` | POST | merchant | 409 if not currently `rejected` |
| `/documents/upload` | POST | merchant | now also 409s if `onboarding_status == "rejected"` |
| `/admin/merchants?status_filter=` | GET | reviewer/admin | optional filter |
| `/admin/merchants/{id}` | GET | reviewer/admin | full detail + audit trail |
| `/admin/exceptions/{id}/resolve` | POST | reviewer/admin | 409 if not currently `flagged` |

---

## 9. Coding rules for this phase (same standards as the rest of the project)

- Strict TypeScript, no `any`, matches `tsconfig.json`'s existing strict settings.
- Every new backend endpoint validates input via a Pydantic schema and returns correct HTTP status codes (400/401/403/404/409) — follow the exact pattern in `auth.py`/`documents.py`.
- Every new frontend API call goes through `api.ts` only; components never call `fetch` directly.
- Every new component is wrapped in `memo()`; every new page handles loading/empty/success/error states via `AsyncState<T>`.
- No hardcoded values — new constants go in `config.py` (backend) or `constants.ts` (frontend).
- No new nested folders — `backend/` stays flat; `frontend/src/` only gets new files inside the existing `components/`/`pages/` folders.
- Block comment at the top of every new file/function explaining purpose, matching the existing docstring style.
- Do not weaken the LLM safety principle anywhere: `humanize_reason` rephrases only, never decides.

---

## 10. Suggested build order

1. `db.py` schema changes → regenerate `schema.sql`
2. `schemas.py` additions
3. `verify.py`: `humanize_reason`
4. `documents.py`: `invalid_format` status, query filters, restart endpoint, upload-blocking, humanize wiring
5. `admin.py`: three new endpoints
6. Frontend: `types.ts` → `constants.ts` → `api.ts` → `VerificationTimeline.tsx` → `StatusBadge.tsx`/`DocumentSlot.tsx` updates → `DashboardPage.tsx` updates → `AdminPage.tsx` → `App.tsx` routing

## 11. Testing checklist (must pass before calling this phase done)

**Backend** (`python -m py_compile *.py`, then exercise via `TestClient`):
- [ ] Uploading a wrong-format document returns `invalid_format`, not `rejected`, and the slot stays uploadable
- [ ] `/documents/restart-application` returns 409 when `onboarding_status != "rejected"`
- [ ] After a successful restart, old documents have `is_active = False` and `GET /documents/merchant-status` returns an empty `documents` list
- [ ] Uploading while `onboarding_status == "rejected"` returns 409
- [ ] `/admin/merchants`, `/admin/merchants/{id}`, `/admin/exceptions/{id}/resolve` all return 403 for a `merchant`-role token
- [ ] `/admin/exceptions/{id}/resolve` returns 409 when the merchant isn't currently `flagged`
- [ ] A resolved-as-rejected merchant has a non-null, humanized `rejection_reason`
- [ ] `humanize_reason` falls back to the original technical string if the API call fails (simulate with a mocked exception)

**Frontend** (`npm run typecheck` must show zero errors, `npm run build` must succeed):
- [ ] `AdminPage` renders each status tab correctly
- [ ] Resolve form only appears for `flagged` merchants
- [ ] `DashboardPage` correctly hides slots and shows the restart button only when `onboarding_status === "rejected"`
- [ ] `VerificationTimeline` renders with zero entries (empty state) without crashing
