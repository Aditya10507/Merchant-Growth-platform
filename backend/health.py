"""
health.py
---------
Process-local system-health metrics powering the admin panel's live
system-health view (Feature 4).

Records per-call outcomes for the two external services the pipeline
depends on — document extraction (OCR/vision, ocr.py) and LLM
cross-verification (verify.py) — plus overall HTTP request outcomes
(main.py middleware), and reports rolling aggregates over a sliding
window: the last HEALTH_WINDOW_SECONDS, capped at MAX_SAMPLES per
stream so a burst cannot grow memory unbounded.

Design notes (mirrors faults.py — same process-local philosophy):
  - Deliberately in-memory and process-local. This view answers "how is
    the system doing RIGHT NOW on this instance", not "what happened
    historically". Render runs a single web process
    (WEB_CONCURRENCY=1), so every request shares this state.
  - Recording is fire-and-forget and never raises: a metrics bug must
    never break a merchant upload or a verification.
  - Zero samples is a valid state ("nothing has run yet on this
    instance") — snapshot() reports count=0 with null rates rather than
    dividing by zero.
"""

import threading
import time
from collections import deque

WINDOW_SECONDS = 3600          # "recent" = the last hour
MAX_SAMPLES = 500              # per stream — bounds memory under bursts

_lock = threading.Lock()
_started_at = time.time()
# (timestamp, ok, latency_ms)
_ocr_samples: deque[tuple[float, bool, float]] = deque()
_llm_samples: deque[tuple[float, bool, float]] = deque()
# (timestamp, http_status, latency_ms)
_request_samples: deque[tuple[float, int, float]] = deque()


def _trim(stream: deque) -> None:
    """Drops samples older than the window and enforces the size cap."""
    cutoff = time.time() - WINDOW_SECONDS
    while stream and stream[0][0] < cutoff:
        stream.popleft()
    while len(stream) > MAX_SAMPLES:
        stream.popleft()


def record_ocr(ok: bool, latency_ms: float) -> None:
    """Records one document-extraction outcome (success or failure)."""
    try:
        with _lock:
            _ocr_samples.append((time.time(), bool(ok), float(latency_ms)))
            _trim(_ocr_samples)
    except Exception:
        pass  # metrics must never break the caller


def record_llm(ok: bool, latency_ms: float) -> None:
    """Records one LLM cross-verification outcome."""
    try:
        with _lock:
            _llm_samples.append((time.time(), bool(ok), float(latency_ms)))
            _trim(_llm_samples)
    except Exception:
        pass


def record_request(status_code: int, latency_ms: float) -> None:
    """Records one HTTP request outcome (status + latency)."""
    try:
        with _lock:
            _request_samples.append((time.time(), int(status_code), float(latency_ms)))
            _trim(_request_samples)
    except Exception:
        pass


def _percentile(latencies: list[float], pct: float) -> float | None:
    """p95-style percentile; None when there are no samples."""
    if not latencies:
        return None
    ordered = sorted(latencies)
    idx = min(len(ordered) - 1, int(len(ordered) * pct))
    return round(ordered[idx], 1)


def _bucket(samples) -> dict:
    """Aggregates one (ts, ok, latency_ms) stream into a summary dict."""
    with _lock:
        _trim(samples)
        items = list(samples)
    if not items:
        return {
            "count": 0, "succeeded": 0, "failed": 0,
            "success_rate": None, "avg_latency_ms": None, "p95_latency_ms": None,
        }
    succeeded = sum(1 for _, ok, _ in items if ok)
    failed = len(items) - succeeded
    latencies = [lat for _, _, lat in items]
    return {
        "count": len(items),
        "succeeded": succeeded,
        "failed": failed,
        "success_rate": round(succeeded / len(items) * 100, 1),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1),
        "p95_latency_ms": _percentile(latencies, 0.95),
    }


def _requests() -> dict:
    """Aggregates HTTP request outcomes into a summary dict."""
    with _lock:
        _trim(_request_samples)
        items = list(_request_samples)
    if not items:
        return {
            "total": 0, "errors_5xx": 0, "error_rate": None, "avg_latency_ms": None,
        }
    errors_5xx = sum(1 for _, status, _ in items if status >= 500)
    latencies = [lat for _, _, lat in items]
    return {
        "total": len(items),
        "errors_5xx": errors_5xx,
        "error_rate": round(errors_5xx / len(items) * 100, 1),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1),
    }


def snapshot() -> dict:
    """Rolling health summary for the admin system-health view."""
    return {
        "uptime_seconds": round(time.time() - _started_at, 1),
        "window_seconds": WINDOW_SECONDS,
        "ocr": _bucket(_ocr_samples),
        "llm": _bucket(_llm_samples),
        "requests": _requests(),
    }


def reset() -> None:
    """Clears all samples (used by tests)."""
    global _started_at
    with _lock:
        _ocr_samples.clear()
        _llm_samples.clear()
        _request_samples.clear()
        _started_at = time.time()