# Demo Video Script (5 minutes)

**Project:** Merchant Onboarding Copilot, Razorpay AI Buildathon 2026 (AI Risk Manager track)
**Total length:** 5 minutes (300 seconds)
**Style:** Simple English. Short sentences. No jargon without a plain explanation.

---

## Timing Plan

| Section | Time | Length | Narration budget |
|---|---|---|---|
| 1. Problem statement | 0:00 to 0:45 | 45 seconds | about 90 words |
| 2. Existing system | 0:45 to 1:25 | 40 seconds | about 80 words |
| 3. Our proposal | 1:25 to 2:10 | 45 seconds | about 95 words |
| 4. How the system is built | 2:10 to 3:05 | 55 seconds | about 100 words |
| 5. How the data flows | 3:05 to 3:50 | 45 seconds | about 90 words |
| 6. Live demo | 3:50 to 5:00 | 70 seconds | about 90 words (rest is screen time) |

**Rule for recording:** read at a calm pace. Pause one second after each on-screen action. If any section runs long, cut its last two sentences, never the live demo.

---

## Section 1: Problem Statement (0:00 to 0:45)

**On screen:** Title card with the project name and "AI Risk Manager Track".

**Narration:**

"When a business wants to accept payments online, the platform must first check who they are. This is called merchant onboarding.

The business uploads a PAN card, a GST certificate, and a bank proof. The platform must check that these documents are real, that they belong to the same person, and that the applicant is not part of a fraud ring.

Today there are two big problems. First, the process is slow. Documents are checked by hand. Second, it is a black box. When an application is flagged, no one can easily explain why. The merchant does not know why, and the platform cannot prove its decision later.

A bad merchant means fraud. A good merchant kept waiting means lost business."

**On screen:** Short text cards as each point is spoken: "Slow", "Black box", "Fraud risk".

---

## Section 2: Existing System (0:45 to 1:25)

**On screen:** Simple diagram showing manual checks, then "Approve or Reject" with no reasons.

**Narration:**

"Here is how onboarding works today.

A reviewer reads each application, compares names and bank details, then types a decision. This is slow, and the queue grows every day.

Some platforms use simple rules instead. But simple rules check only one thing at a time. A format rule cannot catch two documents with different names. It cannot see that ten applicants shared the same bank account.

And automation gives technical messages that merchants cannot understand, so the score stays a mystery."

**On screen:** Show "one check at a time" versus "connected checks".

---

## Section 3: Our Proposal (1:25 to 2:10)

**On screen:** Title card "Our Solution" with four keywords: Read, Connect, Measure, Explain.

**Narration:**

"Our solution automates the checks but keeps a human in charge of the final decision.

First, it reads the documents and extracts the name, PAN, GST number, and bank details.

Second, it connects the dots: five data source checks, the same person across all three documents, and fraud rings where many applicants share one PAN or bank account.

Third, it measures risk. Every application gets a score from 0 to 100, and the system shows exactly which checks failed.

Fourth, it explains. Every score has a breakdown, every decision is stored in an audit trail, and merchants get clear reasons.

The final approve or reject belongs only to a human admin. The AI suggests, the human decides."

**On screen:** Show the four pillars as cards: Read, Connect, Measure, Explain.

---

## Section 4: How the System Is Built (2:10 to 3:05)

**On screen:** The architecture diagram, highlighted step by step.

**Narration:**

"Here is how the system is built.

The front end is a React application for merchants and admins.

The back end is FastAPI, a Python framework, split into small services.

The first service is OCR. It sends each image to the Groq vision model, which reads the fields and returns structured data. Groq is fast and exact.

The second service is the decision engine, the heart of the system. It runs the checks and produces the score. One key choice: the AI only informs, it never decides. The engine is deterministic, so the same input gives the same result.

The third piece is the data layer. PostgreSQL stores merchants, documents, the audit trail, and five simulated external databases.

Everything runs live: backend on Render, frontend on Vercel."

**On screen:** Highlight each block as it is named: Frontend, OCR, Decision Engine, Database.

---

## Section 5: How the Data Flows (3:05 to 3:50)

**On screen:** The sequence diagram, with the three phases named.

**Narration:**

"Let us follow one application.

Phase one: the merchant uploads three documents. Errors show instantly, and when all three pass, the status becomes submitted.

Phase two: the admin clicks Verify. The system runs the AI cross-check, all five external sources, and the fraud-ring scan, then shows which checks matched, which failed, and the risk score.

Phase three: the admin decides. If everything matched, they click Approve. If not, they click Reject, and the merchant sees a plain-language reason.

If a data source is down, the system defers instead of guessing, and the audit trail records everything."

**On screen:** Progress bar through the three phases: Upload, Verify, Decide.

---

## Section 6: Live Demo (3:50 to 5:00)

**On screen:** Live browser on the real deployed site.

**Narration:**

"Now let us show this working live.

I log in as a merchant and upload three documents. Each check finishes in about two to three seconds.

I switch to admin. The panel shows live stats and the new application in the queue.

I open it and click Verify. Here is the breakdown, and here is the risk score.

The documents match, so I approve with one click. Back on the merchant side, the dashboard shows an active account.

That is the complete journey: documents in, risk measured, human decision, clear communication."

**On screen:** Close with a thank-you card and the project name.

---

## Technical Notes for Recording

### What to prepare before recording
- Test documents: use the folder named "Baljit Khan" (clean merchant) or "Manpreet Patel" (flagged merchant). Both are in `test_documents/` or downloadable from the live site at `/test-dataset/download`.
- Demo accounts (quick-fill buttons on the login page speed this up):
  - Merchant: `speed@test.com` / `TestPass123`
  - Admin: `admin@example.com` / `AdminPass123`
  - Reviewer: `reviewer@example.com` / `ReviewerPass123`
- Live URLs to show:
  - Frontend: https://merchant-growth-platform-stct.vercel.app
  - Backend: https://merchant-growth-platform.onrender.com
  - API docs: https://merchant-growth-platform.onrender.com/docs

### Recording tips
- Record at 1080p. Close all other tabs and notifications.
- Pause for one second after each on-screen action before speaking again. Cuts are fine; the video is edited, not one take.
- If a section runs long, trim that section's narration, never the live demo.
- Optional failure-recovery clip (turn off a data source and show the system deferring instead of failing) may be added before Section 6 only if the total still fits in 5 minutes.

### Simple-English checklist
- No emojis, no decorative symbols, no arrows in on-screen text.
- One idea per sentence. Explain any technical word the first time it appears (OCR, audit trail, fraud ring).