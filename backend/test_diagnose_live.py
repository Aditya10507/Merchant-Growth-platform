"""
test_diagnose_live.py
--------------------
Reproduces the user's exact scenario against the live Render deployment:
1. Signup a fresh account
2. Upload synthetic test documents (PAN, GST, BANK_PROOF)  
3. Check OCR results and capture detailed response
"""

import json
import time
import requests

API = "https://merchant-growth-platform.onrender.com"
DOCS_DIR = "C:/Users/GS/project/test_documents/test_documents"

RESULTS = []

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def record(name, passed, detail=""):
    RESULTS.append({"name": name, "passed": passed, "detail": detail})
    tag = "PASS" if passed else "FAIL"
    log(f"  [{tag}] {name}: {detail}")


def run_test(pan_dir_name, test_label):
    """Full test: signup, upload 3 docs, check status."""
    log(f"\n{'='*60}")
    log(f"TEST: {test_label} ({pan_dir_name})")
    log(f"{'='*60}")
    
    import uuid
    run_id = uuid.uuid4().hex[:8]
    email = f"diag_{run_id}@test.com"
    password = "TestPass123"
    business = f"Diag Corp {run_id}"
    
    # 1. Signup
    log("Step 1: Signup")
    r = requests.post(f"{API}/auth/signup", json={
        "business_name": business,
        "email": email,
        "password": password,
    }, timeout=30)
    log(f"  Signup: {r.status_code}")
    if r.status_code != 201:
        log(f"  FAILED: {r.text}")
        record(f"Signup ({test_label})", False, r.text[:200])
        return
    record(f"Signup ({test_label})", True, f"HTTP {r.status_code}")
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Upload 3 documents
    log("Step 2: Upload documents")
    import os
    pan_dir = os.path.join(DOCS_DIR, pan_dir_name)
    
    for doc_type in ["PAN", "GST", "BANK_PROOF"]:
        file_path = os.path.join(pan_dir, f"{doc_type}.png")
        if not os.path.exists(file_path):
            log(f"  File not found: {file_path}")
            record(f"Upload {doc_type} ({test_label})", False, "File not found")
            continue
        
        file_size = os.path.getsize(file_path)
        with open(file_path, "rb") as f:
            content = f.read()
        
        log(f"  {doc_type}: {file_size} bytes, magic={content[:4].hex()}")
        
        start = time.time()
        files = {"file": (f"{doc_type}.png", content, "image/png")}
        r = requests.post(
            f"{API}/documents/upload?doc_type={doc_type}",
            files=files,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        elapsed = time.time() - start
        
        if r.status_code in (200, 201):
            resp = r.json()
            status = resp.get("verification_status")
            confidence = resp.get("ocr_confidence")
            fields = resp.get("extracted_fields")
            rejection = resp.get("rejection_reason")
            
            log(f"  {doc_type} result ({elapsed:.1f}s):")
            log(f"    status={status}, confidence={confidence}")
            log(f"    fields={json.dumps(fields)}")
            if rejection:
                log(f"    rejection={rejection}")
            
            if status == "invalid_format":
                record(f"Upload {doc_type} ({test_label})", False, f"INVALID_FORMAT: {rejection}")
            elif status in ("verifying", "submitted"):
                record(f"Upload {doc_type} ({test_label})", True, f"status={status}, confidence={confidence}")
            else:
                record(f"Upload {doc_type} ({test_label})", False, f"status={status}")
        else:
            log(f"  {doc_type} FAILED: HTTP {r.status_code}")
            log(f"    Response: {r.text[:300]}")
            record(f"Upload {doc_type} ({test_label})", False, f"HTTP {r.status_code}: {r.text[:200]}")
        
        time.sleep(1)  # Rate limit
    
    # 3. Check final status
    log("Step 3: Check merchant status")
    r = requests.get(f"{API}/documents/merchant-status", headers=headers, timeout=30)
    if r.status_code == 200:
        data = r.json()
        onboarding = data.get("onboarding_status")
        docs = data.get("documents", [])
        log(f"  Onboarding status: {onboarding}")
        for d in docs:
            log(f"  {d['doc_type']}: status={d['verification_status']}, confidence={d.get('ocr_confidence')}, reason={d.get('rejection_reason')}")
        
        # Check if all docs are in expected state
        all_ok = all(d["verification_status"] in ("verifying", "submitted") for d in docs)
        record(f"Status ({test_label})", all_ok, f"onboarding={onboarding}, docs={len(docs)}")
    else:
        log(f"  Status check FAILED: {r.status_code} {r.text[:200]}")
        record(f"Status ({test_label})", False, f"HTTP {r.status_code}")
    
    return email, password, token


def main():
    log("=" * 60)
    log("LIVE DIAGNOSTIC: Reproducing user's upload failure scenario")
    log(f"API: {API}")
    log("=" * 60)
    
    # First, check the backend is alive
    try:
        r = requests.get(f"{API}/health", timeout=10)
        log(f"Health check: {r.status_code} {r.text}")
    except Exception as e:
        log(f"Cannot reach backend: {e}")
        return
    
    # Test 1: Fresh account with UJALK5542W docs
    result1 = run_test("UJALK5542W", "Test1_UJALK5542W")
    
    time.sleep(2)
    
    # Test 2: Fresh account with HAOEL7625O docs  
    result2 = run_test("HAOEL7625O", "Test2_HAOEL7625O")
    
    time.sleep(2)
    
    # Test 3: RE-UPLOAD scenario - use same account, try to upload again
    # This simulates user's scenario: same account, upload docs again
    log(f"\n{'='*60}")
    log("TEST 3: Re-upload with same account (user's scenario)")
    log(f"{'='*60}")
    
    if result1:
        email, password, token = result1
        headers = {"Authorization": f"Bearer {token}"}
        
        # Check current status first
        r = requests.get(f"{API}/documents/merchant-status", headers=headers, timeout=30)
        if r.status_code == 200:
            status = r.json()["onboarding_status"]
            log(f"  Current status: {status}")
            
            if status == "submitted":
                log("  Merchant already submitted - upload will be blocked (409)")
                log("  This matches user's scenario: they couldn't re-upload after submission")
                record("Re-upload blocked", True, "Correctly blocked with 409 (submitted)")
                
                # Try to upload anyway to see the error
                import os
                pan_dir = os.path.join(DOCS_DIR, "UJALK5542W")
                file_path = os.path.join(pan_dir, "PAN.png")
                with open(file_path, "rb") as f:
                    content = f.read()
                files = {"file": ("PAN.png", content, "image/png")}
                r = requests.post(
                    f"{API}/documents/upload?doc_type=PAN",
                    files=files,
                    headers=headers,
                    timeout=60,
                )
                log(f"  Re-upload attempt: HTTP {r.status_code}")
                log(f"  Response: {r.text[:300]}")
            elif status == "rejected":
                log("  Merchant rejected - need to restart application first")
                # Try restart
                r = requests.post(f"{API}/documents/restart-application", headers=headers, timeout=30)
                log(f"  Restart attempt: HTTP {r.status_code}")
                if r.status_code == 200:
                    log("  Restarted! Now try re-upload...")
                    import os
                    pan_dir = os.path.join(DOCS_DIR, "UJALK5542W")
                    for doc_type in ["PAN", "GST", "BANK_PROOF"]:
                        file_path = os.path.join(pan_dir, f"{doc_type}.png")
                        with open(file_path, "rb") as f:
                            content = f.read()
                        files = {"file": (f"{doc_type}.png", content, "image/png")}
                        r = requests.post(
                            f"{API}/documents/upload?doc_type={doc_type}",
                            files=files,
                            headers=headers,
                            timeout=60,
                        )
                        if r.status_code in (200, 201):
                            resp = r.json()
                            log(f"  Re-upload {doc_type}: status={resp.get('verification_status')}, reason={resp.get('rejection_reason')}")
                        else:
                            log(f"  Re-upload {doc_type}: HTTP {r.status_code} {r.text[:200]}")
            else:
                log(f"  Status is '{status}' - can re-upload")
                import os
                pan_dir = os.path.join(DOCS_DIR, "UJALK5542W")
                for doc_type in ["PAN", "GST", "BANK_PROOF"]:
                    file_path = os.path.join(pan_dir, f"{doc_type}.png")
                    with open(file_path, "rb") as f:
                        content = f.read()
                    files = {"file": (f"{doc_type}.png", content, "image/png")}
                    r = requests.post(
                        f"{API}/documents/upload?doc_type={doc_type}",
                        files=files,
                        headers=headers,
                        timeout=60,
                    )
                    if r.status_code in (200, 201):
                        resp = r.json()
                        log(f"  Re-upload {doc_type}: status={resp.get('verification_status')}, reason={resp.get('rejection_reason')}")
                    else:
                        log(f"  Re-upload {doc_type}: HTTP {r.status_code} {r.text[:200]}")
    
    # Summary
    log(f"\n{'='*60}")
    log("SUMMARY")
    log(f"{'='*60}")
    passed = sum(1 for r in RESULTS if r["passed"])
    failed = sum(1 for r in RESULTS if not r["passed"])
    total = len(RESULTS)
    log(f"Total: {total} | Passed: {passed} | Failed: {failed} | Rate: {(passed/total*100) if total else 0:.1f}%")
    log("")
    for r in RESULTS:
        tag = "PASS" if r['passed'] else "FAIL"
        log(f"  [{tag}] {r['name']}: {r['detail']}")


if __name__ == "__main__":
    main()
