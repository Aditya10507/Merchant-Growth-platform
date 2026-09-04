# UI/UX Document
## Merchant Onboarding Copilot
**Version:** 2.0 (kept current; shipped monochrome enterprise interface)

---

## 1. Design Principles

- **Clarity over decoration.** Merchants and admins always know what is happening and why.
- **Fast feedback.** Validate at the point of action: instant upload results, instant verify and decide responses.
- **Monochrome enterprise look.** Strictly Tailwind's black, white, and gray scale. This is a deliberate choice, not a brand clone.
- **Transparency.** Every rejection, flag, and deferral shows a plain-language reason. Admins see the full structured breakdown behind every score.
- **Accessibility.** Status is never conveyed by color alone. Every control is keyboard-navigable with visible labels.

## 2. App Shell

- Three top-level views routed by session role in `App.tsx`: AuthPage (no session), merchant DashboardPage, and AdminPage for reviewers or admins.
- All authenticated screens sit inside `Layout.tsx`, a sidebar shell.

## 3. Screens

| Screen | Who | Purpose |
|---|---|---|
| AuthPage | Everyone | Signup and login with demo quick-fill buttons for merchant, reviewer, and admin accounts |
| DashboardPage | Merchant | The 3 document slots (PAN, GST, Bank Proof), live status polling (4s), active and rejected states |
| AdminPage | Reviewer/admin | Review queue, detail panel, and real-time stats dashboard |

## 4. Merchant Dashboard

- Three upload slots, one per document type. Each shows its own document state: empty, uploading or checking, valid, `invalid_format` (retry), `temporarily_unavailable` (try again in a moment), or rejected.
- Instant feedback on upload: a success alert on clean extraction, a clear "invalid document, please check and try again" alert on `invalid_format`, and a retry-friendly message on `temporarily_unavailable`.
- Once all 3 documents are valid, the merchant reaches `submitted` and sees a neutral "under review" state. No internal check details are ever shown to the merchant.
- When rejected: the upload grid hides, the plain-language `rejection_reason` shows, and a "Start a new application" button restarts the flow (old documents are retired, not deleted).
- When active: a success banner shows and the upload grid hides.

## 5. Admin/Reviewer Panel (AdminPage)

### 5.0 Real-time stats dashboard (top strip)
- Live counters that update in real time. The panel polls `GET /admin/stats` every few seconds and refreshes immediately after every verify, approve, or reject action.
- Cards: Applicants (pending + submitted + verified), Approvals (active merchants), Rejections, Flagged percentage (mismatched or flagged over all processed), Fraud-ring flagged, and Fraud-ring rate.
- Numbers move the moment the data changes. No manual refresh. The strip always matches the queue.

### 5.1 Review queue
- Three simple tabs: Applicants (pending, submitted, and verified states with one comma-separated status filter), Active merchants (approved accounts), and Rejected.
- Merchant table columns: business name, status badge, risk badge, and submitted date. The View button opens the detail pane.
- No engineering cards in the panel. Chaos toggles, calibration, and health stay as backend endpoints and API docs (Session 26).

### 5.2 Detail panel (stationary side pane)
- Merchant identity, status, and risk badge. Documents show extracted fields and OCR confidence.
- When submitted, a "Verify with internal databases" button runs the LLM check, the 5 sources, and the fraud-ring scan. On deferral it shows the clear message and the merchant stays submitted.
- Fraud-ring analysis: a dedicated section, visible once verification has run, lists every `fraud_ring_*` check. It says "no shared identifiers" when clean, or an explicit flagged summary when the applicant shares a PAN or bank identifier with other applications.
- When verified_matching: fraud-ring section, matched-checks list, and a one-click "Approve and activate account" button.
- When verified_mismatched: fraud-ring section, passed-checks list, failed-checks list (fraud-ring and prompt-injection findings visually highlighted), a risk-score breakdown with points per check, an editable rejection message pre-filled from the auto-drafted cause, and a "Reject and notify merchant" button.
- Approve and reject record the decision and its message. The merchant dashboard reflects it immediately, with an active banner or the rejection reason.
- The audit trail renders as a timeline of labeled actions with reasons and timestamps.

## 6. States

| State | Behavior |
|---|---|
| Loading | Table or card-level status text such as "Loading merchants", never a blank screen |
| Empty | "No merchants found for this filter". Empty check lists render as italic "No ..." notes |
| Error | Inline error alert with the API's detail message, plus retry where sensible |
| Success | Success alerts after decisions and maintenance actions |

All async flows follow the shared `AsyncState<T>` pattern (idle, loading, success, error). No ad-hoc boolean flags.

## 7. Layout and Responsive Behavior

- The app shell is a fixed-viewport dashboard (sidebar and main area), not a long scrollable page. The admin header and tabs stay pinned. The review area below flexes: the merchant queue table and the stationary detail pane each scroll internally (`overflow-y-auto` with a sticky table header), so clicking View never scrolls the detail away.
- The admin queue and detail panel sit side by side on wide screens with a fixed-width detail column. Tables scroll instead of squeezing on narrow viewports.
- Dashboard slots: three across on desktop, wrapping to one on mobile.

## 8. Accessibility and Interaction Notes

- StatusBadge pairs color with text. RiskBadge shows the numeric score plus a level label such as "Low risk".
- Tabs use `aria-pressed`.
- Tables and buttons are keyboard-navigable with visible focus states throughout.
- Components are memoized. The dashboard polls every 4 seconds, a deliberate balance between liveness and load.
