# UI/UX Document
## Merchant Onboarding Copilot
**Version:** 2.0 (kept current — shipped monochrome enterprise interface)

---

## 1. Design Principles

- **Clarity over decoration** — merchants and admins always know what's happening and why
- **Fast feedback** — validate at the point of action (instant upload results, instant verify/decide responses)
- **Monochrome enterprise aesthetic** — strictly Tailwind's black/white/gray scale (deliberately not a brand clone; removed the earlier teal palette)
- **Transparency** — every rejection/flag/deferral shows a plain-language reason; admins see the full structured breakdown behind every score
- **Accessibility** — status never conveyed by color alone; every control keyboard-navigable with visible labels

## 2. App Shell

- Three top-level views routed by session role (`App.tsx`): **AuthPage** (no session) → merchant **DashboardPage** / reviewer-or-admin **AdminPage**.
- All authenticated screens sit inside `Layout.tsx` (sidebar shell).

## 3. Screens

| Screen | Who | Purpose |
|---|---|---|
| AuthPage | everyone | Signup/login; demo quick-fill buttons for merchant / reviewer / admin accounts |
| DashboardPage | merchant | The 3 document slots (PAN, GST, Bank Proof), live status polling (4s), active/rejected states |
| AdminPage | reviewer/admin | Review queue + detail panel + admin-only engineering cards |

## 4. Merchant Dashboard

- Three upload slots, one per document type; each shows its per-document state: empty → uploading/`verifying` → `approved`/`invalid_format` (retry) / `temporarily_unavailable` (try again in a moment) / `rejected`.
- Instant feedback on upload response: a success/valid alert on clean extraction, a clear "invalid document — please check and try again" alert on `invalid_format`, and a retry-friendly message on `temporarily_unavailable`.
- Once all 3 documents are valid the merchant reaches `submitted` and sees a neutral "under review" state — **no internal check details are ever shown to the merchant**.
- `rejected`: the upload grid hides, the plain-language `rejection_reason` shows, and a **"Start a new application"** button restarts the flow (old documents retired, not deleted).
- `active`: success/activated banner, upload grid hidden.

## 5. Admin/Reviewer Panel (AdminPage)

### 5.1 Review queue
- Three simple tabs (Session 26 — the panel is intentionally minimal): **Applicants** (pending/submitted/verified states, one comma-separated status filter), **Active merchants** (approved accounts), **Rejected**.
- Merchant table: business, status badge, **risk badge**, submitted date; the **View** button opens the detail pane. No engineering cards in the panel — chaos/calibration/health stay as backend endpoints + `/docs` (Session 26).

### 5.2 Detail panel (stationary side pane)
- Merchant identity + status + risk badge; documents with extracted fields and OCR confidence.
- **submitted** → **"Verify with internal databases"** button (runs LLM + 5 sources + fraud-ring scan; on deferral shows the 503 message and the merchant stays submitted).
- **Fraud-ring analysis** — a dedicated section (visible once verification has run) lists every `fraud_ring_*` check: "no shared identifiers" when clean, an explicit flagged summary when the applicant shares PAN/bank identifiers with other applications.
- **verified_matching** → fraud-ring section + matched-checks list + one-click **"Approve & activate account"**.
- **verified_mismatched** → fraud-ring section, passed-checks list, failed-checks list (fraud-ring and prompt-injection findings visually highlighted), risk-score breakdown (points per check), editable rejection message pre-filled from the auto-drafted cause, **"Reject & notify merchant"**.
- Approve/reject records the decision and its message; the merchant's dashboard reflects it immediately (`active` banner or `rejection_reason`).
- Audit trail rendered as a timeline of labeled actions with reasons and timestamps.

## 6. States

| State | Behavior |
|---|---|
| Loading | Table/card-level status text ("Loading merchants…") — never blank |
| Empty | "No merchants found for this filter"; empty check lists render as italic "No …" notes |
| Error | Inline `Alert variant="error"` with the API's detail message + retry where sensible |
| Success | Green/gray success alerts after decisions and maintenance actions |

All async flows follow the shared `AsyncState<T>` pattern (idle/loading/success/error) — no ad-hoc boolean flags.

## 7. Layout & Responsive Behavior

- The app shell is a **fixed-viewport dashboard** (sidebar + main), not a long scrollable page: the admin header and tabs are pinned, and the review row below flexes — the merchant queue table and the stationary detail pane each scroll *internally* (`overflow-y-auto` + sticky table header), so clicking "View" never scrolls the detail away.
- Admin queue + detail panel sit side by side on wide screens (fixed-width detail column); tables scroll rather than squeeze on narrow viewports.
- Dashboard slots: 3-up on desktop, wrapping to 1-up on mobile.

## 8. Accessibility & Interaction Notes

- StatusBadge pairs color with text; RiskBadge shows the numeric score + a level label ("Low risk" etc.).
- Tabs use `aria-pressed`.
- Keyboard-navigable tables/buttons; visible focus states throughout.
- Components are memoized; the dashboard polls at 4s — a deliberate balance between liveness and load.
