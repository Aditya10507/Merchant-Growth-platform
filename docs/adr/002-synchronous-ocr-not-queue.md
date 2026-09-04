# ADR-002: Synchronous OCR with in-request retries instead of a background queue

- **Status:** Accepted
- **Date:** 2026-09-04
- **Applies to:** `backend/ocr.py`, `backend/documents.py`

## Context

Document extraction (OCR/vision) takes 1–10 seconds per document. A
textbook design puts it on a background worker with a job queue and
webhooks. But the free tier of our host (Render) gives one small web
process with no guaranteed background workers — a background thread
is killed on deploy/restart, and a job queue (Redis/Celery) is a whole
infrastructure we'd be paying for and operating for a demo.

## Decision

Extraction is **synchronous within the upload request**, with:
- retries + exponential backoff on transient failures (rate limit,
  network, 5xx),
- multi-key rotation across Groq accounts on 401/403/429,
- retry-friendly statuses (`temporarily_unavailable` instead of a hard
  rejection) when the service truly won't cooperate.

The upload endpoint returns the extraction outcome inline; the merchant's
dashboard polls `merchant-status` and shows a live "verifying" state.

## Consequences

- **Simple deploy:** one process, no queue, no workers, no webhook
  plumbing. The whole pipeline survives a cold start.
- Upload latency is bounded by extraction time (~seconds) — acceptable
  for a human uploading 3 documents, and the UI covers it with a
  verifying state.
- Throughput is limited to ~1 document per few seconds (pacing) — fine
  for a human-driven onboarding flow, wrong for bulk ingestion (out of
  scope).
- Failure recovery is explicit and visible: the "retry in a moment" path
  is first-class, not an afterthought.