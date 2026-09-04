# ADR-002: Synchronous OCR with in-request retries instead of a background queue

- **Status:** Accepted
- **Date:** 2026-09-04
- **Applies to:** `backend/ocr.py`, `backend/documents.py`

## Context

Document extraction (OCR/vision) takes 1 to 10 seconds per document. A textbook design puts it on a background worker with a job queue and webhooks. But the free tier of our host (Render) provides one small web process with no guaranteed background workers. A background thread is killed on deploy or restart, and a job queue (Redis/Celery) is infrastructure we would be paying for and operating just for a demo.

## Decision

Extraction is synchronous within the upload request, with:
- retries and exponential backoff on transient failures (rate limit, network, 5xx),
- multi-key rotation across Groq accounts on 401/403/429,
- retry-friendly statuses (`temporarily_unavailable` instead of a hard rejection) when the service truly will not cooperate.

The upload endpoint returns the extraction outcome inline. The merchant dashboard polls `merchant-status` and shows a live checking state.

## Consequences

- **Simple deploy.** One process, no queue, no workers, no webhook plumbing. The whole pipeline survives a cold start.
- Upload latency is bounded by extraction time (a few seconds). That is acceptable for a human uploading 3 documents, and the UI covers it with a checking state.
- Throughput is limited to about 1 document per few seconds (pacing). That is fine for a human-driven onboarding flow and wrong for bulk ingestion (out of scope).
- Failure recovery is explicit and visible. The "try again in a moment" path is a first-class feature, not an afterthought.
