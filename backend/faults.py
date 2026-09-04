"""
faults.py
---------
Demo-only fault injection for the buildathon's "Failure Recovery" story.

An admin (never a reviewer/merchant) can toggle simulated outages in the
admin panel. The app code checks `faults.is_active(...)` at the exact
boundaries where a real outage would occur (OCR engine, LLM API,
external verification sources) and then exercises the SAME graceful
degradation paths a real outage would: retry-friendly statuses, deferred
verification with audit-trail reasons, and clean recovery once the fault
is cleared.

This is deliberately in-memory and process-local:
  - Toggles reset on redeploy/restart — a demo can never get stuck.
  - Render runs a single web process (WEB_CONCURRENCY=1), so state is
    shared across requests within the running instance.
  - Faults NEVER touch the database or real API calls — they only change
    what the code paths do at the boundary, exactly like a real outage.

Supported faults:
  - ocr_down        → uploads surface the retry-friendly
                      "temporarily_unavailable" status (Session 18 path).
  - llm_down        → admin verification is DEFERRED (no determination is
                      made on partial signals); retry after clearing.
  - sources_down    → the 5 external sources raise
                      decision.ExternalSourceUnavailableError → verify is
                      deferred with an audit-trail reason, same as llm_down.
"""

import threading

SUPPORTED_FAULTS = ("ocr_down", "llm_down", "sources_down")

_lock = threading.Lock()
_active: set[str] = set()


def is_active(fault_name: str) -> bool:
    """True while the named fault is toggled on."""
    with _lock:
        return fault_name in _active


def set_fault(fault_name: str, enabled: bool) -> bool:
    """Turns a fault on/off. Returns True if the state actually changed.

    Raises ValueError for unknown fault names (fail fast — a typo should
    never silently toggle nothing).
    """
    if fault_name not in SUPPORTED_FAULTS:
        raise ValueError(
            f"Unknown fault '{fault_name}'. Supported: {', '.join(SUPPORTED_FAULTS)}"
        )
    with _lock:
        changed = (fault_name in _active) != enabled
        if enabled:
            _active.add(fault_name)
        else:
            _active.discard(fault_name)
    return changed


def snapshot() -> dict[str, bool]:
    """Current state of every supported fault, for the admin panel."""
    with _lock:
        return {name: name in _active for name in SUPPORTED_FAULTS}


def reset_all() -> list[str]:
    """Clears every fault. Returns the faults that were active (now cleared)."""
    global _active
    with _lock:
        cleared = sorted(_active)
        _active.clear()
    return cleared
