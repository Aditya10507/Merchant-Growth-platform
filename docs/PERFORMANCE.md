# Performance and Reliability Evidence

Measured against the live deployed backend (Render) and the real Groq vision API
(`qwen/qwen3.8-27b`), not a mock. All numbers come from actual runs logged in
`session_log.md` (Sessions 23-27).

---

## 1. Document Verification Latency (upload to extracted)

Target: every document verifies in 3 to 4 seconds or less, including back-to-back uploads.

| Document | Upload to verified latency | Extraction result (exact match) |
|---|---|---|
| PAN | 2.92s | `AGSFS4133P / Anirban Rathore / 26/11/2001` |
| GST | 1.98s | `27AGSFS4133P1Z5 / Rathore Grocery Depot` |
| BANK_PROOF | 2.41s | `CNRB0268893 / 288845758260 / Anirban Rathore` |

Independent baseline runs in a clean quota window: GST 3.38s, BANK_PROOF 2.42s, PAN 3.03s,
with the same exact extractions.

**Back-to-back burst:** with the 3-key rotation pool, all three documents upload one after
another at the latencies above. Each request starts as the previous one finishes, so a full
3-document application verifies in about 7 to 9 seconds total.

### What made this possible
- Image downscaling and JPEG re-encoding before the vision call (payload-latency optimization).
- OCR moved off the event loop with bounded concurrency and request pacing.
- A per-request fail-fast timeout that honors `Retry-After`.

## 2. OCR and Verification Accuracy

| Metric | Value |
|---|---|
| Batch accuracy report (`/admin/batch-test`) | 100% |
| Ground-truth merchants scored | 25 (15 approve, 10 flag) |
| False approvals | 0 |
| Unresolved exceptions | 0 |
| Offline feature suite (`test_features.py`) | 83/83 checks |

The batch test replays the real deterministic decision engine against 25 seeded merchants
with hand-labeled expected outcomes. The accuracy number comes from the same code path judges
will demo, not from a test double.

## 3. Reliability Engineering

| Failure mode | Mitigation | Demonstrated |
|---|---|---|
| Groq daily quota exhaustion (about 200K tokens/day) | `LLM_FALLBACK_KEYS` rotation pool (3 accounts, roughly 250 uploads/day); 429/401/403 triggers rotation | Live-tested with the primary key fully exhausted; all 3 documents extracted exactly through fallback keys |
| Transient OCR provider outage | `temporarily_unavailable` status with self-healing re-extraction on the next status poll after cooldown | Offline suite Feature 8 |
| LLM or external-source outage | Verification defers (503), the merchant stays `submitted`, audit-logged. Never scores on partial signals | Offline suite Feature 1 |
| Two admins deciding at the same time | Atomic single-winner state transition (the loser gets a 409), exactly one audit entry | Offline suite Feature 4 |
| Prompt injection in uploaded documents | Sanitized before the LLM sees it, audit-logged, routed to human review | Offline suite Feature 3 |
| Stale documents shadowing re-uploads | Re-upload retires the previous active same-type document | Offline suite Feature 7 |

## 4. Known Constraints (honest limitations)

- **Fixed token cost per vision call.** Groq charges about 2,113 tokens per call regardless of
  image resolution or detail level (verified empirically at 300-1000px). Downscaling trims
  payload latency only; it does not stretch the daily budget. Hard ceiling: about 83 uploads
  per day per Groq account, about 250 per day with the 3-key rotation pool.
- **Simulated external sources.** The 5 validation sources (govt DB, CKYC, etc.) are
  deterministic simulators with documented behavior. Real integrations are the documented
  production path (ADR-002, ADR-005).
- **Process-local demo state.** Failure toggles and health metrics reset on restart (ADR-007).
  This is intentional for demo safety, not historical telemetry.

---

*Generated 2026-09-04. Measurement methodology: real uploads against the deployed API;
latencies are wall-clock time from upload to the verified response.*
