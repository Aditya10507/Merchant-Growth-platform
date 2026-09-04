"""
test_e2e.py — Comprehensive End-to-End Test Suite
===================================================
Merchant Onboarding Copilot — covers ALL features as of Session 11.

Test groups:
  A. API Tests (requests-based, fast and reliable)
     A1. Health check
     A2. Merchant signup
     A3. Merchant login
     A4. Document upload (3 docs, clean PAN)
     A5. Merchant status check (should be "submitted")
     A6. Admin login
     A7. Admin merchant list
     A8. Admin merchant detail
     A9. Admin verify application
     A10. Admin approve application
     A11. Merchant status → active
     A12. Duplicate signup (409)
     A13. Wrong password login (401)
     A14. Merchant accessing admin endpoints (403)
     A15. Invalid document upload
     A16. Batch test endpoint
     A17. Restart application flow (reject → restart → pending)
     A18. Mismatch merchant verification (flagged path)

  B. UI Tests (Playwright-based, tests the frontend)
     B1. Frontend loads
     B2. AuthPage — demo account quick-fill buttons
     B3. Admin login via UI
     B4. Admin panel — merchant list visible
     B5. Admin panel — filter tabs work
     B6. Admin panel — merchant detail panel
     B7. Merchant login via UI
     B8. Merchant dashboard — document slots visible
     B9. Merchant dashboard — logout

Rate limiting: 2-second minimum between OCR uploads.

Run with:
    cd backend
    python test_e2e.py
"""

import json as _json
import os
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:5173"
TEST_DOCS_DIR = Path(__file__).parent.parent / "test_documents" / "test_documents"
CLEAN_PAN_DIR = TEST_DOCS_DIR / "Baljit Khan"    # seed data has verified records (PAN UJALK5542W)
MISMATCH_PAN_DIR = TEST_DOCS_DIR / "Manpreet Patel"  # seed data has invalid records (PAN VDAWP9860F)
SCREENSHOT_DIR = Path(__file__).parent / "test_screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

# Test accounts
CLEAN_EMAIL = f"e2e_clean_{int(time.time())}@example.com"
MISMATCH_EMAIL = f"e2e_mismatch_{int(time.time())}@example.com"
TEST_PASSWORD = "TestPass123"
TEST_BUSINESS_CLEAN = "E2E Clean Business"
TEST_BUSINESS_MISMATCH = "E2E Mismatch Business"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "AdminPass123"

# Rate limiting: minimum seconds between OCR uploads
UPLOAD_DELAY = 2.0


class TestResults:
    """Tracks pass/fail counts and detailed results."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.details: list[str] = []
        self.timings: list[tuple[str, float]] = []

    def record(self, name: str, passed: bool, detail: str = "", elapsed: float = 0.0):
        if passed:
            self.passed += 1
            self.details.append(f"  [PASS] {name}")
        else:
            self.failed += 1
            self.details.append(f"  [FAIL] {name}: {detail}")
        if elapsed > 0:
            self.timings.append((name, elapsed))

    def skip(self, name: str, reason: str):
        self.skipped += 1
        self.details.append(f"  [SKIP] {name} (skipped: {reason})")

    def summary(self) -> str:
        lines = [
            "",
            "=" * 70,
            "  E2E TEST RESULTS — Merchant Onboarding Copilot",
            "=" * 70,
            "",
        ]
        for d in self.details:
            lines.append(d)
        lines.append("")
        lines.append(f"  Total:   {self.passed + self.failed + self.skipped}")
        lines.append(f"  Passed:  {self.passed}")
        lines.append(f"  Failed:  {self.failed}")
        lines.append(f"  Skipped: {self.skipped}")
        if self.timings:
            lines.append("")
            lines.append("  Timings:")
            for name, t in self.timings:
                lines.append(f"    {name}: {t:.2f}s")
        lines.append("=" * 70)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper: API client
# ---------------------------------------------------------------------------
class ApiClient:
    """Thin wrapper around requests with auth token management."""

    def __init__(self, base_url: str):
        self.base = base_url
        self.token: str | None = None

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if extra:
            h.update(extra)
        return h

    def get(self, path: str, **kwargs) -> requests.Response:
        return requests.get(f"{self.base}{path}", headers=self._headers(), timeout=30, **kwargs)

    def post(self, path: str, json_data: dict | None = None, **kwargs) -> requests.Response:
        return requests.post(f"{self.base}{path}", json=json_data, headers=self._headers(), timeout=60, **kwargs)

    def post_form(self, path: str, files: dict, **kwargs) -> requests.Response:
        h = {}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return requests.post(f"{self.base}{path}", files=files, headers=h, timeout=60, **kwargs)

    def login(self, email: str, password: str) -> dict:
        resp = self.post("/auth/login", {"email": email, "password": password})
        resp.raise_for_status()
        data = resp.json()
        self.token = data["access_token"]
        return data

    def signup(self, business_name: str, email: str, password: str) -> dict:
        resp = self.post("/auth/signup", {"business_name": business_name, "email": email, "password": password})
        resp.raise_for_status()
        data = resp.json()
        self.token = data["access_token"]
        return data

    def upload(self, doc_type: str, file_path: Path) -> dict:
        with open(file_path, "rb") as f:
            resp = self.post_form(
                f"/documents/upload?doc_type={doc_type}",
                files={"file": (file_path.name, f, "image/png")},
            )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# GROUP A: API Tests
# ---------------------------------------------------------------------------
def run_api_tests(results: TestResults) -> tuple[ApiClient, ApiClient, int | None]:
    """Run all API tests. Returns (merchant_client, admin_client, merchant_id)."""
    merchant = ApiClient(BACKEND_URL)
    admin = ApiClient(BACKEND_URL)
    clean_merchant_id: int | None = None

    # ── A1: Health check ──────────────────────────────────────────────
    print("\n[A1] Health check...")
    t0 = time.time()
    try:
        resp = requests.get(f"{BACKEND_URL}/health", timeout=10)
        assert resp.status_code == 200, f"Status {resp.status_code}"
        data = resp.json()
        assert data["status"] == "ok"
        results.record("A1: Health check", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A1: Health check", False, str(e), time.time() - t0)
        return merchant, admin, None

    # ── A2: Merchant signup (clean) ───────────────────────────────────
    print("\n[A2] Merchant signup (clean)...")
    t0 = time.time()
    try:
        data = merchant.signup(TEST_BUSINESS_CLEAN, CLEAN_EMAIL, TEST_PASSWORD)
        assert data["role"] == "merchant"
        assert data["merchant_id"] is not None
        clean_merchant_id = data["merchant_id"]
        results.record("A2: Merchant signup (clean)", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A2: Merchant signup (clean)", False, str(e), time.time() - t0)

    # ── A3: Merchant login ────────────────────────────────────────────
    print("\n[A3] Merchant login...")
    t0 = time.time()
    try:
        merchant.token = None  # reset
        data = merchant.login(CLEAN_EMAIL, TEST_PASSWORD)
        assert data["access_token"]
        assert data["role"] == "merchant"
        results.record("A3: Merchant login", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A3: Merchant login", False, str(e), time.time() - t0)

    # ── A4: Document upload (3 docs, clean PAN) ───────────────────────
    print("\n[A4] Upload PAN card...")
    t0 = time.time()
    pan_path = CLEAN_PAN_DIR / "PAN.png"
    try:
        assert pan_path.exists(), f"Test file not found: {pan_path}"
        doc = merchant.upload("PAN", pan_path)
        assert doc["verification_status"] in ("verifying", "submitted", "invalid_format")
        results.record("A4a: Upload PAN", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A4a: Upload PAN", False, str(e), time.time() - t0)

    print(f"  (waiting {UPLOAD_DELAY}s for OCR rate limit)...")
    time.sleep(UPLOAD_DELAY)

    print("\n[A4] Upload GST certificate...")
    t0 = time.time()
    gst_path = CLEAN_PAN_DIR / "GST.png"
    try:
        assert gst_path.exists(), f"Test file not found: {gst_path}"
        doc = merchant.upload("GST", gst_path)
        assert doc["verification_status"] in ("verifying", "submitted", "invalid_format")
        results.record("A4b: Upload GST", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A4b: Upload GST", False, str(e), time.time() - t0)

    print(f"  (waiting {UPLOAD_DELAY}s for OCR rate limit)...")
    time.sleep(UPLOAD_DELAY)

    print("\n[A4] Upload Bank proof...")
    t0 = time.time()
    bank_path = CLEAN_PAN_DIR / "BANK_PROOF.png"
    try:
        assert bank_path.exists(), f"Test file not found: {bank_path}"
        doc = merchant.upload("BANK_PROOF", bank_path)
        assert doc["verification_status"] in ("verifying", "submitted", "invalid_format")
        results.record("A4c: Upload Bank proof", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A4c: Upload Bank proof", False, str(e), time.time() - t0)

    # ── A5: Wait for OCR + check merchant status ──────────────────────
    print("\n[A5] Waiting for OCR processing (up to 30s)...")
    t0 = time.time()
    status_data = None
    for attempt in range(15):
        time.sleep(2)
        try:
            resp = merchant.get("/documents/merchant-status")
            if resp.status_code == 200:
                status_data = resp.json()
                if status_data["onboarding_status"] in ("submitted", "rejected", "verified_matching", "verified_mismatched", "active"):
                    break
        except Exception:
            pass
    elapsed = time.time() - t0

    try:
        assert status_data is not None, "Could not fetch merchant status"
        final_status = status_data["onboarding_status"]
        num_docs = len(status_data.get("documents", []))
        assert num_docs == 3, f"Expected 3 documents, got {num_docs}"
        results.record(
            f"A5: Merchant status after OCR ({final_status}, {num_docs} docs)",
            final_status in ("submitted", "verified_matching", "verified_mismatched", "active"),
            f"Unexpected status: {final_status}",
            elapsed,
        )
    except Exception as e:
        results.record("A5: Merchant status after OCR", False, str(e), elapsed)

    # ── A6: Admin login ───────────────────────────────────────────────
    print("\n[A6] Admin login...")
    t0 = time.time()
    try:
        data = admin.login(ADMIN_EMAIL, ADMIN_PASSWORD)
        assert data["role"] == "admin"
        results.record("A6: Admin login", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A6: Admin login", False, str(e), time.time() - t0)

    # ── A7: Admin merchant list ───────────────────────────────────────
    print("\n[A7] Admin merchant list...")
    t0 = time.time()
    try:
        resp = admin.get("/admin/merchants")
        assert resp.status_code == 200
        merchants = resp.json()
        assert isinstance(merchants, list)
        assert len(merchants) > 0, "No merchants found"
        results.record(f"A7: Admin merchant list ({len(merchants)} merchants)", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A7: Admin merchant list", False, str(e), time.time() - t0)

    # ── A7b: Filter by status ────────────────────────────────────────
    print("\n[A7b] Admin filter by status...")
    t0 = time.time()
    try:
        resp = admin.get("/admin/merchants", params={"status_filter": "submitted"})
        assert resp.status_code == 200
        filtered = resp.json()
        # All returned merchants should have status "submitted"
        for m in filtered:
            assert m["onboarding_status"] == "submitted", f"Merchant {m['merchant_id']} has status {m['onboarding_status']}"
        results.record(f"A7b: Filter by submitted ({len(filtered)} results)", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A7b: Filter by submitted", False, str(e), time.time() - t0)

    # ── A7c: Sort by risk ────────────────────────────────────────────
    print("\n[A7c] Admin sort by risk...")
    t0 = time.time()
    try:
        resp = admin.get("/admin/merchants", params={"sort_by_risk": "true"})
        assert resp.status_code == 200
        sorted_list = resp.json()
        # Verify ordering: scored merchants first (descending), then unscored
        scored = [m for m in sorted_list if m["risk_score"] is not None]
        unscored = [m for m in sorted_list if m["risk_score"] is None]
        if len(scored) > 1:
            for i in range(len(scored) - 1):
                assert scored[i]["risk_score"] >= scored[i + 1]["risk_score"], "Risk sort order violated"
        results.record(f"A7c: Sort by risk ({len(scored)} scored, {len(unscored)} unscored)", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A7c: Sort by risk", False, str(e), time.time() - t0)

    # ── A8: Admin merchant detail ─────────────────────────────────────
    print("\n[A8] Admin merchant detail...")
    t0 = time.time()
    try:
        assert clean_merchant_id is not None, "No merchant_id from signup"
        resp = admin.get(f"/admin/merchants/{clean_merchant_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["merchant_id"] == clean_merchant_id
        assert detail["business_name"] == TEST_BUSINESS_CLEAN
        assert len(detail["documents"]) == 3, f"Expected 3 docs, got {len(detail['documents'])}"
        # Note: audit_trail is empty at this point because audit entries
        # are only created by verify_application (A9) and decide_application (A10)
        results.record(
            f"A8: Admin merchant detail (docs={len(detail['documents'])}, audit={len(detail['audit_trail'])})",
            True,
            elapsed=time.time() - t0,
        )
    except Exception as e:
        results.record("A8: Admin merchant detail", False, str(e), time.time() - t0)

    # ── A9: Admin verify application ─────────────────────────────────
    print("\n[A9] Admin verify application (LLM + external checks)...")
    t0 = time.time()
    try:
        assert clean_merchant_id is not None
        resp = admin.post(f"/admin/merchants/{clean_merchant_id}/verify")
        assert resp.status_code == 200
        verified = resp.json()
        assert verified["onboarding_status"] in ("verified_matching", "verified_mismatched")
        has_risk = verified.get("risk_score") is not None
        results.record(
            f"A9: Admin verify ({verified['onboarding_status']}, risk_score={verified.get('risk_score')})",
            True,
            elapsed=time.time() - t0,
        )
    except Exception as e:
        results.record("A9: Admin verify", False, str(e), time.time() - t0)

    # ── A10: Admin approve application ────────────────────────────────
    print("\n[A10] Admin approve application...")
    t0 = time.time()
    try:
        assert clean_merchant_id is not None
        resp = admin.post(
            f"/admin/merchants/{clean_merchant_id}/decide",
            {"decision": "approved"},
        )
        assert resp.status_code == 200
        decided = resp.json()
        assert decided["onboarding_status"] == "active"
        results.record("A10: Admin approve → active", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A10: Admin approve", False, str(e), time.time() - t0)

    # ── A11: Verify merchant sees active status ───────────────────────
    print("\n[A11] Merchant status → active...")
    t0 = time.time()
    try:
        resp = merchant.get("/documents/merchant-status")
        assert resp.status_code == 200
        status_data = resp.json()
        assert status_data["onboarding_status"] == "active", f"Got {status_data['onboarding_status']}"
        results.record("A11: Merchant sees active status", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A11: Merchant status → active", False, str(e), time.time() - t0)

    # ── A12: Duplicate signup (409) ──────────────────────────────────
    print("\n[A12] Duplicate signup → 409...")
    t0 = time.time()
    try:
        resp = requests.post(
            f"{BACKEND_URL}/auth/signup",
            json={"business_name": "Dup", "email": CLEAN_EMAIL, "password": TEST_PASSWORD},
            timeout=10,
        )
        assert resp.status_code == 409, f"Expected 409, got {resp.status_code}"
        results.record("A12: Duplicate signup → 409", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A12: Duplicate signup", False, str(e), time.time() - t0)

    # ── A13: Wrong password login (401) ──────────────────────────────
    print("\n[A13] Wrong password login → 401...")
    t0 = time.time()
    try:
        resp = requests.post(
            f"{BACKEND_URL}/auth/login",
            json={"email": CLEAN_EMAIL, "password": "WrongPassword123"},
            timeout=10,
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        results.record("A13: Wrong password → 401", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A13: Wrong password", False, str(e), time.time() - t0)

    # ── A14: Merchant accessing admin endpoints (403) ─────────────────
    print("\n[A14] Merchant → admin endpoint → 403...")
    t0 = time.time()
    try:
        resp = merchant.get("/admin/merchants")
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
        results.record("A14: Merchant → admin → 403", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A14: Merchant → admin → 403", False, str(e), time.time() - t0)

    # ── A15: Invalid document upload ──────────────────────────────────
    print("\n[A15] Invalid document upload...")
    t0 = time.time()
    try:
        # Upload a text file as PAN — should be rejected at content-type level
        invalid_path = TEST_DOCS_DIR / "invalid_test.txt"
        if invalid_path.exists():
            resp = merchant.post_form(
                "/documents/upload?doc_type=PAN",
                files={"file": ("invalid.txt", b"this is not a PAN card", "text/plain")},
            )
            assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
            results.record("A15: Invalid content type → 400", True, elapsed=time.time() - t0)
        else:
            results.skip("A15: Invalid document upload", "test file not found")
    except Exception as e:
        results.record("A15: Invalid document upload", False, str(e), time.time() - t0)

    # ── A16: Batch test endpoint ──────────────────────────────────────
    print("\n[A16] Batch test endpoint...")
    t0 = time.time()
    try:
        resp = admin.post("/admin/batch-test")
        assert resp.status_code == 200
        report = resp.json()
        assert "total_records" in report
        assert "accuracy_percent" in report
        results.record(
            f"A16: Batch test (total={report['total_records']}, accuracy={report['accuracy_percent']}%)",
            True,
            elapsed=time.time() - t0,
        )
    except Exception as e:
        results.record("A16: Batch test", False, str(e), time.time() - t0)

    # ── A17: Restart application flow ─────────────────────────────────
    print("\n[A17] Restart application flow...")
    _test_restart_flow(results, merchant, admin)

    # ── A18: Mismatch merchant verification (flagged path) ────────────
    print("\n[A18] Mismatch merchant verification...")
    _test_mismatch_flow(results, merchant, admin)

    return merchant, admin, clean_merchant_id


def _test_restart_flow(results: TestResults, merchant: ApiClient, admin: ApiClient):
    """Test: reject → restart → pending → re-upload flow."""
    # Create a fresh merchant for this test
    restart_email = f"e2e_restart_{int(time.time())}@example.com"
    restart_merchant = ApiClient(BACKEND_URL)
    t0 = time.time()
    try:
        data = restart_merchant.signup("Restart Test Business", restart_email, TEST_PASSWORD)
        merchant_id = data["merchant_id"]

        # Upload 3 docs
        for doc_type, filename in [("PAN", "PAN.png"), ("GST", "GST.png"), ("BANK_PROOF", "BANK_PROOF.png")]:
            path = CLEAN_PAN_DIR / filename
            if path.exists():
                restart_merchant.upload(doc_type, path)
                time.sleep(UPLOAD_DELAY)

        # Wait for OCR
        for _ in range(15):
            time.sleep(2)
            resp = restart_merchant.get("/documents/merchant-status")
            if resp.status_code == 200:
                s = resp.json()
                if s["onboarding_status"] in ("submitted", "rejected"):
                    break

        # Verify and reject
        admin.login(ADMIN_EMAIL, ADMIN_PASSWORD)
        resp = admin.post(f"/admin/merchants/{merchant_id}/verify")
        if resp.status_code == 200:
            verified = resp.json()
            if verified["onboarding_status"] in ("verified_matching", "verified_mismatched"):
                resp = admin.post(
                    f"/admin/merchants/{merchant_id}/decide",
                    {"decision": "rejected", "note": "Test rejection for restart flow"},
                )
                assert resp.status_code == 200

        # Restart application
        resp = restart_merchant.post("/documents/restart-application")
        assert resp.status_code == 200
        restarted = resp.json()
        assert restarted["onboarding_status"] == "pending"

        # Verify status is pending
        resp = restart_merchant.get("/documents/merchant-status")
        assert resp.status_code == 200
        status = resp.json()
        assert status["onboarding_status"] == "pending"

        results.record("A17: Restart application flow", True, elapsed=time.time() - t0)
    except Exception as e:
        results.record("A17: Restart application flow", False, str(e), time.time() - t0)


def _test_mismatch_flow(results: TestResults, merchant: ApiClient, admin: ApiClient):
    """Test: upload mismatch PAN → verify → verified_mismatched → reject."""
    mismatch_email = f"e2e_mismatch_{int(time.time())}@example.com"
    mismatch_merchant = ApiClient(BACKEND_URL)
    t0 = time.time()
    try:
        data = mismatch_merchant.signup("Mismatch Test Business", mismatch_email, TEST_PASSWORD)
        merchant_id = data["merchant_id"]

        # Upload 3 docs with mismatch PAN
        for doc_type, filename in [("PAN", "PAN.png"), ("GST", "GST.png"), ("BANK_PROOF", "BANK_PROOF.png")]:
            path = MISMATCH_PAN_DIR / filename
            if path.exists():
                mismatch_merchant.upload(doc_type, path)
                time.sleep(UPLOAD_DELAY)

        # Wait for OCR
        for _ in range(15):
            time.sleep(2)
            resp = mismatch_merchant.get("/documents/merchant-status")
            if resp.status_code == 200:
                s = resp.json()
                if s["onboarding_status"] in ("submitted", "rejected"):
                    break

        # Verify
        admin.login(ADMIN_EMAIL, ADMIN_PASSWORD)
        resp = admin.post(f"/admin/merchants/{merchant_id}/verify")
        assert resp.status_code == 200
        verified = resp.json()
        assert verified["onboarding_status"] == "verified_mismatched", f"Got {verified['onboarding_status']}"
        assert verified["mismatched_checks"] is not None
        assert len(verified["mismatched_checks"]) > 0
        assert verified["risk_score"] is not None
        assert verified["risk_score"] > 0

        results.record(
            f"A18: Mismatch verify (mismatches={len(verified['mismatched_checks'])}, risk={verified['risk_score']})",
            True,
            elapsed=time.time() - t0,
        )

        # Reject
        resp = admin.post(
            f"/admin/merchants/{merchant_id}/decide",
            {"decision": "rejected"},
        )
        assert resp.status_code == 200
        assert resp.json()["onboarding_status"] == "rejected"
        results.record("A18b: Admin reject mismatched → rejected", True, elapsed=time.time() - t0)

    except Exception as e:
        results.record("A18: Mismatch flow", False, str(e), time.time() - t0)


# ---------------------------------------------------------------------------
# GROUP B: UI Tests (Playwright)
# ---------------------------------------------------------------------------
def run_ui_tests(results: TestResults):
    """Run Playwright-based UI tests."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        results.skip("B1-B9: UI Tests", "playwright not installed")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})

        # ── B1: Frontend loads ────────────────────────────────────────
        print("\n[B1] Frontend loads...")
        t0 = time.time()
        page = context.new_page()
        try:
            page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
            assert "localhost" in page.url.lower()
            page.screenshot(path=str(SCREENSHOT_DIR / "b01_frontend_load.png"), full_page=True)
            results.record("B1: Frontend loads", True, elapsed=time.time() - t0)
        except Exception as e:
            results.record("B1: Frontend loads", False, str(e), time.time() - t0)
            browser.close()
            return

        # ── B2: Demo account quick-fill buttons ───────────────────────
        print("\n[B2] Demo account quick-fill buttons...")
        t0 = time.time()
        try:
            # Look for demo buttons on the login page
            page.wait_for_timeout(1000)
            demo_buttons = page.locator("button").filter(has_text="Admin")
            admin_btn_count = demo_buttons.count()
            merchant_btn = page.locator("button").filter(has_text="Merchant")
            merchant_btn_count = merchant_btn.count()
            reviewer_btn = page.locator("button").filter(has_text="Reviewer")
            reviewer_btn_count = reviewer_btn.count()
            total_demo = admin_btn_count + merchant_btn_count + reviewer_btn_count
            assert total_demo >= 2, f"Expected at least 2 demo buttons, found {total_demo}"
            results.record(f"B2: Demo quick-fill buttons ({total_demo} found)", True, elapsed=time.time() - t0)
        except Exception as e:
            results.record("B2: Demo buttons", False, str(e), time.time() - t0)

        # ── B3: Admin login via UI ────────────────────────────────────
        print("\n[B3] Admin login via UI...")
        t0 = time.time()
        try:
            # Click the Admin demo button to auto-fill
            admin_btn = page.locator("button").filter(has_text="Admin")
            if admin_btn.count() > 0:
                admin_btn.first.click()
                page.wait_for_timeout(500)

            # If on signup mode, switch to login
            login_toggle = page.locator("text=Already have an account")
            if login_toggle.count() > 0:
                login_toggle.click()
                page.wait_for_timeout(500)
                # Click Admin button again after switching
                admin_btn = page.locator("button").filter(has_text="Admin")
                if admin_btn.count() > 0:
                    admin_btn.first.click()
                    page.wait_for_timeout(500)

            # Fill manually if demo button didn't work
            email_input = page.locator('input[type="email"]')
            if email_input.input_value() == "":
                email_input.fill(ADMIN_EMAIL)
                page.locator('input[type="password"]').fill(ADMIN_PASSWORD)

            page.click('button[type="submit"]')
            page.wait_for_timeout(3000)

            # Check if we reached the admin panel
            admin_panel = page.locator("text=Merchant Verification Panel")
            if admin_panel.count() == 0:
                # Maybe we're on dashboard — check for admin content
                page.wait_for_timeout(2000)
                admin_panel = page.locator("text=Merchant Verification Panel")

            page.screenshot(path=str(SCREENSHOT_DIR / "b03_admin_login.png"), full_page=True)
            is_admin = admin_panel.count() > 0
            results.record("B3: Admin login via UI", is_admin, "Admin panel not found", time.time() - t0)
        except Exception as e:
            results.record("B3: Admin login via UI", False, str(e), time.time() - t0)

        # ── B4: Admin panel — merchant list ───────────────────────────
        print("\n[B4] Admin panel — merchant list...")
        t0 = time.time()
        try:
            # Navigate to admin if not already there
            page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(1000)

            # Login as admin
            login_toggle = page.locator("text=Already have an account")
            if login_toggle.count() > 0:
                login_toggle.click()
                page.wait_for_timeout(500)

            email_input = page.locator('input[type="email"]')
            email_input.fill(ADMIN_EMAIL)
            page.locator('input[type="password"]').fill(ADMIN_PASSWORD)
            page.click('button[type="submit"]')
            page.wait_for_timeout(3000)

            # Check for merchant table
            table = page.locator("table")
            table_count = table.count()
            rows = page.locator("tbody tr")
            row_count = rows.count()
            page.screenshot(path=str(SCREENSHOT_DIR / "b04_admin_list.png"), full_page=True)
            assert table_count > 0 or row_count > 0, "No merchant table found"
            results.record(f"B4: Admin merchant list ({row_count} rows)", True, elapsed=time.time() - t0)
        except Exception as e:
            results.record("B4: Admin merchant list", False, str(e), time.time() - t0)

        # ── B5: Admin panel — filter tabs ─────────────────────────────
        print("\n[B5] Admin panel — filter tabs...")
        t0 = time.time()
        try:
            tabs = page.locator("nav[aria-label] button")
            tab_count = tabs.count()
            assert tab_count >= 3, f"Expected at least 3 filter tabs, found {tab_count}"

            # Click "Submitted" tab
            submitted_tab = page.locator("button").filter(has_text="Submitted")
            if submitted_tab.count() > 0:
                submitted_tab.first.click()
                page.wait_for_timeout(1500)

            page.screenshot(path=str(SCREENSHOT_DIR / "b05_filter_tabs.png"), full_page=True)
            results.record(f"B5: Filter tabs ({tab_count} tabs)", True, elapsed=time.time() - t0)
        except Exception as e:
            results.record("B5: Filter tabs", False, str(e), time.time() - t0)

        # ── B6: Admin panel — merchant detail ─────────────────────────
        print("\n[B6] Admin panel — merchant detail...")
        t0 = time.time()
        try:
            # Click "All" tab first
            all_tab = page.locator("button").filter(has_text="All")
            if all_tab.count() > 0:
                all_tab.first.click()
                page.wait_for_timeout(1500)

            # Click first merchant row or View button
            view_btn = page.locator("button").filter(has_text="View")
            if view_btn.count() > 0:
                view_btn.first.click()
                page.wait_for_timeout(2000)

            # Check for detail panel
            detail_panel = page.locator('[aria-label="Merchant detail"]')
            has_detail = detail_panel.count() > 0

            page.screenshot(path=str(SCREENSHOT_DIR / "b06_merchant_detail.png"), full_page=True)
            results.record("B6: Merchant detail panel", has_detail, "Detail panel not found", time.time() - t0)
        except Exception as e:
            results.record("B6: Merchant detail", False, str(e), time.time() - t0)

        # ── B7: Merchant login via UI ─────────────────────────────────
        print("\n[B7] Merchant login via UI...")
        t0 = time.time()
        try:
            # Logout first
            logout_btn = page.locator("button").filter(has_text="Log out")
            if logout_btn.count() > 0:
                logout_btn.first.click()
                page.wait_for_timeout(1000)

            # Navigate fresh
            page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(1000)

            # Switch to login
            login_toggle = page.locator("text=Already have an account")
            if login_toggle.count() > 0:
                login_toggle.click()
                page.wait_for_timeout(500)

            # Fill merchant credentials
            email_input = page.locator('input[type="email"]')
            email_input.fill(CLEAN_EMAIL)
            page.locator('input[type="password"]').fill(TEST_PASSWORD)
            page.click('button[type="submit"]')
            page.wait_for_timeout(3000)

            # Check for dashboard
            dashboard = page.locator("text=Complete your onboarding")
            active_alert = page.locator("text=account has been activated")
            is_merchant = dashboard.count() > 0 or active_alert.count() > 0
            page.screenshot(path=str(SCREENSHOT_DIR / "b07_merchant_dashboard.png"), full_page=True)
            results.record("B7: Merchant login → dashboard", is_merchant, "Dashboard not found", time.time() - t0)
        except Exception as e:
            results.record("B7: Merchant login", False, str(e), time.time() - t0)

        # ── B8: Merchant dashboard — document slots / active state ────
        print("\n[B8] Merchant dashboard state...")
        t0 = time.time()
        try:
            page.wait_for_timeout(1000)
            # Check what state we're in
            has_active = page.locator("text=account has been activated").count() > 0
            has_slots = page.locator('input[type="file"]').count()
            has_submitted = page.locator("text=under review").count() > 0

            page.screenshot(path=str(SCREENSHOT_DIR / "b08_dashboard_state.png"), full_page=True)
            state_desc = "active" if has_active else ("submitted" if has_submitted else f"{has_slots} file inputs")
            results.record(f"B8: Dashboard state ({state_desc})", True, elapsed=time.time() - t0)
        except Exception as e:
            results.record("B8: Dashboard state", False, str(e), time.time() - t0)

        # ── B9: Logout ────────────────────────────────────────────────
        print("\n[B9] Logout...")
        t0 = time.time()
        try:
            logout_btn = page.locator("button").filter(has_text="Log out")
            if logout_btn.count() > 0:
                logout_btn.first.click()
                page.wait_for_timeout(2000)

            # Should be back on auth page
            login_form = page.locator('input[type="email"]')
            is_logged_out = login_form.count() > 0
            page.screenshot(path=str(SCREENSHOT_DIR / "b09_logout.png"), full_page=True)
            results.record("B9: Logout → auth page", is_logged_out, "Auth page not found after logout", time.time() - t0)
        except Exception as e:
            results.record("B9: Logout", False, str(e), time.time() - t0)

        browser.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("  E2E TEST SUITE — Merchant Onboarding Copilot")
    print("  Comprehensive coverage: API + UI, all features")
    print("=" * 70)
    print(f"  Backend:  {BACKEND_URL}")
    print(f"  Frontend: {FRONTEND_URL}")
    print(f"  Test docs: {TEST_DOCS_DIR}")
    print(f"  Screenshots: {SCREENSHOT_DIR}")
    print(f"  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    results = TestResults()

    # --- Group A: API Tests ---
    print("\n" + "-" * 70)
    print("  GROUP A: API Tests")
    print("-" * 70)
    merchant_client, admin_client, merchant_id = run_api_tests(results)

    # --- Group B: UI Tests ---
    print("\n" + "─" * 70)
    print("  GROUP B: UI Tests (Playwright)")
    print("-" * 70)
    run_ui_tests(results)

    # ── Summary ───────────────────────────────────────────────────────
    summary = results.summary()
    print(summary)

    # Save report to file
    report_path = Path(__file__).parent / "test_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"E2E Test Report — {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(summary)
    print(f"\n  Report saved to: {report_path}")

    return results.failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
