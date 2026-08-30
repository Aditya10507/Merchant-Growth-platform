# UI/UX Document
## Merchant Onboarding Copilot
**Version:** 1.0 (lean, implementation-ready)

---

## 1. Design Principles

- **Clarity over decoration** — merchants should always know what's happening and why
- **Fast feedback** — validate at the point of action (e.g., wrong document type flagged instantly)
- **Razorpay-inspired, not cloned** — use a similar clean, card-based, teal/blue palette and typography feel without copying logos or exact layouts
- **Transparency** — every rejection/flag shows a plain-language reason, never a silent failure

## 2. User Journey

1. Merchant lands on signup page → creates account
2. Redirected to onboarding dashboard → sees 3 empty document slots (PAN, GST, Bank Proof)
3. Uploads each document → gets instant client-side feedback (valid type / wrong type)
4. Submits → sees a "verifying" status per document
5. Backend processes → dashboard updates to Approved / Flagged / Rejected per document
6. Once all 3 are approved → merchant sees "Account activated" screen with next steps
7. If flagged → merchant sees a plain-language reason and a "re-upload" or "contact support" option

## 3. Screens

| Screen | Purpose |
|---|---|
| Signup / Login | Account creation and access |
| Onboarding Dashboard | Central hub — 3 document slots with status |
| Document Upload Modal | Upload + instant type validation |
| Verification Status | Per-document detail: extracted fields, confidence, decision reason |
| Account Activated | Success state, entry point to "merchant home" |
| Exception/Flagged View | Shown when a document needs review or re-upload |
| Reviewer Panel (internal) | List of flagged merchants with reasons (separate role) |
| Batch Test Report (internal/demo) | Shows accuracy metrics for judges/demo |

## 4. Navigation

- Simple top nav: Logo | Dashboard | Support | Account menu
- No deep navigation tree needed — MVP is a linear flow (upload → verify → activate)
- Reviewer panel is a separate route (`/reviewer`), gated by role

## 5. Core Components

- **Document upload card** — icon, slot label (e.g., "PAN Card"), drag-and-drop or click-to-upload, status badge (empty / uploaded / verifying / approved / flagged)
- **Status badge** — color-coded pill: gray (empty), blue (verifying), green (approved), amber (flagged), red (rejected)
- **Reason panel** — expandable section showing plain-language explanation + extracted fields
- **Progress stepper** — shows overall onboarding progress (3 steps: Upload → Verify → Activate)
- **Toast/inline alerts** — for instant client-side validation errors

## 6. Forms

- Signup: email, password, business name (minimal fields for MVP)
- Document upload: file picker per slot, accepts JPG/PNG/PDF, 5MB max, inline error if wrong format/size

## 7. Loading / Error / Empty States

| State | Behavior |
|---|---|
| Empty | Document slot shows placeholder icon + "Upload your PAN card" prompt |
| Loading (client-side check) | Small spinner on the upload card while type check runs |
| Loading (backend verification) | "Verifying..." badge with subtle pulse animation |
| Error (wrong doc type) | Immediate inline red message: "This looks like an Aadhaar card. Please upload your PAN card." |
| Error (backend/API failure) | "Something went wrong — we're retrying" with auto-retry, then manual review fallback message |
| Flagged | Amber badge + plain-language reason + "Re-upload" button |
| Success | Green badge + checkmark, all 3 slots green triggers "Account Activated" screen |

## 8. Responsive Behavior

- Desktop: 3 document slots shown side-by-side in a row
- Tablet: 2 per row, wrapping
- Mobile: single column, one slot per row, sticky "Submit" button at bottom

## 9. Accessibility

- All status badges paired with text labels, not color alone
- Form fields have visible labels (not placeholder-only)
- Sufficient contrast for status colors (use darker shade of each color for text on colored backgrounds)
- Keyboard-navigable upload controls and buttons

## 10. Typography & Colors

- **Typography:** clean sans-serif (e.g., Inter or system-ui), single weight scale (regular/medium), sentence case for all labels
- **Colors:** teal/blue primary (Razorpay-inspired), neutral grays for structure, semantic colors for status (green = approved, amber = flagged, red = rejected, blue = in progress)
- **Spacing:** consistent 8px base spacing unit; cards use generous padding (16–24px) to avoid a cramped, dense look

## 11. Interaction Notes

- Uploading a document triggers immediate client-side check before any backend call — this is the single most "wow" interaction for the demo, so it should feel instant
- Status transitions (verifying → approved/flagged) should update live if possible (polling every few seconds is sufficient for MVP; no need for websockets)
