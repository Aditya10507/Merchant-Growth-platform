# 📊 Performance & Reliability Evidence

Measured against the **live deployed backend** (Render) and the **real Groq vision API**
(`qwen/qwen3.8-27b`) — not a mock. All numbers are from actual runs logged in
`session_log.md` (Sessions 23–27).

---

## 1. Document Verification Latency (upload → extracted)

Target: **every document verifiable in ≤ 3–4 seconds**, including back-to-back uploads.

| Document | Upload → verified latency | Extraction result (exact match) |
|---|---|---|
| **PAN** | **2.92s** | `AGSFS4133P / Anirban Rathore / 26/11/2001` ✅ |
| **GST** | **1.98s** | `27AGSFS4133P1Z5 / Rathore Grocery Depot` ✅ |
| **BANK_PROOF** | **2.41s** | `CNRB0268893 / 288845758260 / Anirban Rathore` ✅ |

Independent baseline runs (clean quota window): GST **3.38s**, BANK_PROOF **2.42s**, PAN **3.03s** — same exact extractions.

**Back-to-back burst:** with the 3-key rotation pool, all three documents upload sequentially at the latencies above — each request starts as the previous finishes, so a full 3-document application verifies in **~7–9s total**.

### What made this possible
- Image downscaling + JPEG re-encode before the vision call (payload-latency optimization)
- OCR moved off the event loop with bounded concurrency + request pacing
- Per-request fail-fast timeout + `Retry-After` honoring

## 2. OCR / Verification Accuracy

| Metric | Value |
|---|---|
| Batch accuracy report (`/admin/batch-test`) | **100%** |
| Ground-truth merchants scored | **25** (15 approve / 10 flag) |
| False approvals | **0** |
| Unresolved exceptions | **0** |
| Offline feature suite (`test_features.py`) | **83/83 checks** |

The batch-test replays the real deterministic decision engine against 25 seeded
merchants with hand-labeled expected outcomes — the accuracy number is produced by
the same code path judges will demo, not a test double.

## 3. Reliability Engineering

| Failure mode | Mitigation | Demonstrated |
|---|---|---|
| Groq daily quota exhaustion (~200K tokens/day) | `LLM_FALLBACK_KEYS` rotation pool (3 accounts ≈ 250 uploads/day); 429/401/403 triggers rotation | Live-tested with primary key fully exhausted — all 3 docs extracted exactly through fallback keys |
| Transient OCR provider outage | `temporarily_unavailable` status, **self-healing re-extraction** on next status poll after cooldown | Offline suite Feature 8 |
| LLM / external-source outage | Verification **defers** (503, merchant stays `submitted`, audit-logged) — never scores on partial signals | Offline suite Features 1 |
| Two admins deciding simultaneously | Atomic single-winner state transition (loser gets 409), exactly one audit entry | Offline suite Feature 4 |
| Prompt injection in uploaded documents | Sanitized before the LLM sees it, audit-logged, routes to human review | Offline suite Feature 3 |
| Stale documents shadowing re-uploads | Re-upload retires the previous active same-type doc | Offline suite Feature 7 |

## 4. Known Constraints (honest limitations)

- **Fixed token cost per vision call**: Groq charges ~2,113 tokens per call regardless
  of image resolution or `detail` level (verified empirically at 300–1000px). Downscaling
  trims payload latency only — it does **not** stretch the daily budget. Hard ceiling:
  ~83 uploads/day per Groq account, ~250/day with the 3-key rotation pool.
- **Simulated external sources**: the 5 validation sources (govt DB, CKYC, etc.) are
  deterministic simulators with documented behavior — real integrations are the
  documented production path (ADR-002, ADR-005).
- **Process-local demo state**: chaos fault toggles and health metrics reset on restart
  (ADR-007) — intentional for demo safety, not historical telemetry.

---

*Generated 2026-09-04. Measurement methodology: real uploads against the deployed API; latencies are wall-clock upload → verified response.*