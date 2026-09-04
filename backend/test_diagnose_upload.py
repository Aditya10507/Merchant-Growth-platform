"""
test_diagnose_upload.py
-----------------------
Reproduces the user's exact scenario:
1. Signup a fresh account
2. Upload synthetic test documents (PAN, GST, BANK_PROOF)
3. Capture detailed OCR response to find why "No readable text found"
"""

import json
import os
import sys
import time
import traceback
from pathlib import Path

# Force local SQLite (real LLM_API_KEY/vision key comes from backend/.env)
os.environ["DATABASE_URL"] = "sqlite:///./test_diagnose.db"
os.environ["JWT_SECRET_KEY"] = "test_diagnose_key_1234567890abcdef"

# Load .env values
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# Override DATABASE_URL for local test
os.environ["DATABASE_URL"] = "sqlite:///./test_diagnose.db"

from config import settings
# Force SQLite
settings.DATABASE_URL = "sqlite:///./test_diagnose.db"

import ocr
import documents
from db import SessionLocal, init_db, Merchant, Document
from auth import hash_password

DOCS_DIR = Path(__file__).parent.parent / "test_documents" / "test_documents"

# Test merchants to simulate the user's scenario
TEST_MERCHANTS = [
    {"name": "Diag Test Corp A", "email": "diag_test_a@diagnose.com", "password": "TestPass123", "pan": "UJALK5542W"},
    {"name": "Diag Test Corp B", "email": "diag_test_b@diagnose.com", "password": "TestPass123", "pan": "HAOEL7625O"},
]

RESULTS = []


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def record(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append({"name": name, "passed": passed, "detail": detail})
    log(f"  {'✅' if passed else '❌'} {name}: {detail}")


def test_direct_ocr(doc_type, file_path):
    """Directly run vision extraction on a file and capture the result."""
    log(f"\n  --- Direct Extraction Test: {doc_type} ({file_path.name}) ---")
    log(f"  File size: {file_path.stat().st_size} bytes")
    
    # Read file to check type
    with open(file_path, "rb") as f:
        header = f.read(8)
    log(f"  File header bytes: {header[:8].hex()}")
    is_pdf = header[:4] == b"%PDF"
    log(f"  Is PDF: {is_pdf}")
    
    try:
        # Call extraction directly (Groq vision)
        fields, confidence, raw_text = ocr.extract_structured_fields(str(file_path), doc_type)
        log(f"  Fields: {json.dumps(fields, indent=2)}")
        log(f"  Confidence: {confidence}")
        log(f"  Raw text (first 500 chars): {raw_text[:500]}")
        return fields, confidence, raw_text
    except Exception as e:
        log(f"  Extraction EXCEPTION: {e}")
        traceback.print_exc()
        return None


def test_structured_extraction(doc_type, file_path):
    """Test the full structured extraction pipeline."""
    log(f"\n  --- Structured Extraction: {doc_type} ---")
    try:
        fields, confidence, raw_text = ocr.extract_structured_fields(str(file_path), doc_type)
        log(f"  Fields: {json.dumps(fields, indent=2)}")
        log(f"  Confidence: {confidence}")
        log(f"  Raw text: {raw_text[:500]}")
        log(f"  Raw text empty: {not raw_text.strip()}")
        return fields, confidence, raw_text
    except Exception as e:
        log(f"  Extraction EXCEPTION: {e}")
        traceback.print_exc()
        return None, 0, ""


def test_format_check(raw_text, doc_type):
    """Test the format matching logic."""
    import re
    signatures = {
        "PAN": re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]"),
        "GST": re.compile(settings.GST_REGEX.strip("^$")),
        "BANK_PROOF": re.compile(r"[A-Z]{4}0[A-Z0-9]{6}"),
    }
    sig = signatures.get(doc_type)
    if sig:
        match = sig.search(raw_text)
        log(f"  Format check for {doc_type}: {'MATCH' if match else 'NO MATCH'}")
        if match:
            log(f"  Matched: {match.group(0)}")
        return bool(match)
    return True


def test_full_upload_flow(merchant_email, merchant_password, pan_dir):
    """Simulate the complete upload flow like the frontend does."""
    import requests
    
    log(f"\n{'='*60}")
    log(f"Testing full upload flow for {merchant_email}")
    log(f"Test documents directory: {pan_dir}")
    log(f"{'='*60}")
    
    # 1. Login
    API = "http://localhost:8000"
    r = requests.post(f"{API}/auth/login", json={"email": merchant_email, "password": merchant_password})
    if r.status_code != 200:
        log(f"Login failed: {r.status_code} {r.text}")
        return
    token = r.json()["access_token"]
    log(f"Login successful, token received")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Upload each document type
    for doc_type in ["PAN", "GST", "BANK_PROOF"]:
        file_path = pan_dir / f"{doc_type}.png"
        if not file_path.exists():
            log(f"  File not found: {file_path}")
            continue
        
        log(f"\n  Uploading {doc_type}...")
        log(f"  File: {file_path}")
        log(f"  File size: {file_path.stat().st_size} bytes")
        
        # Read file content
        with open(file_path, "rb") as f:
            content = f.read()
        log(f"  First 16 bytes: {content[:16].hex()}")
        png_magic = content[:4] == b'\x89PNG'
        jpeg_magic = content[:2] == b'\xff\xd8'
        pdf_magic = content[:4] == b'%PDF'
        log(f"  Is PNG: {png_magic}")
        log(f"  Is JPEG: {jpeg_magic}")
        log(f"  Is PDF: {pdf_magic}")
        
        # Upload via multipart (like the frontend does)
        start = time.time()
        files = {"file": (f"{doc_type}.png", content, "image/png")}
        r = requests.post(
            f"{API}/documents/upload?doc_type={doc_type}",
            files=files,
            headers={"Authorization": f"Bearer {token}"},
        )
        elapsed = time.time() - start
        log(f"  Upload response: {r.status_code} ({elapsed:.1f}s)")
        
        if r.status_code in (200, 201):
            resp = r.json()
            log(f"  Status: {resp.get('verification_status')}")
            log(f"  OCR confidence: {resp.get('ocr_confidence')}")
            log(f"  Extracted fields: {json.dumps(resp.get('extracted_fields'), indent=2)}")
            log(f"  Rejection reason: {resp.get('rejection_reason')}")
            
            status = resp.get("verification_status")
            if status == "invalid_format":
                log(f"  ❌ DOCUMENT REJECTED AS INVALID FORMAT")
                log(f"  Reason: {resp.get('rejection_reason')}")
                record(f"Upload {doc_type}", False, f"invalid_format: {resp.get('rejection_reason')}")
            elif status == "verifying":
                log(f"  ⏳ Still verifying (OCR might be slow)")
                record(f"Upload {doc_type}", True, "verifying (OCR in progress)")
            elif status == "submitted":
                log(f"  ✅ Document passed OCR and format check")
                record(f"Upload {doc_type}", True, "submitted")
            else:
                log(f"  Status: {status}")
                record(f"Upload {doc_type}", False, f"unexpected status: {status}")
        else:
            log(f"  Upload FAILED: {r.text}")
            record(f"Upload {doc_type}", False, f"HTTP {r.status_code}: {r.text[:200]}")
    
    # 3. Check final merchant status
    log(f"\n  --- Final Merchant Status ---")
    r = requests.get(f"{API}/documents/merchant-status", headers=headers)
    if r.status_code == 200:
        status = r.json()
        log(f"  Onboarding status: {status.get('onboarding_status')}")
        log(f"  Documents: {len(status.get('documents', []))}")
        for doc in status.get("documents", []):
            log(f"    {doc['doc_type']}: {doc['verification_status']} (confidence={doc.get('ocr_confidence')})")
            if doc.get("rejection_reason"):
                log(f"      Reason: {doc['rejection_reason']}")
    else:
        log(f"  Status check failed: {r.status_code} {r.text}")


def main():
    log("=" * 60)
    log("DIAGNOSTIC TEST: Reproducing user's upload failure scenario")
    log("=" * 60)
    
    # Setup fresh database
    db_path = Path(__file__).parent / "test_diagnose.db"
    if db_path.exists():
        db_path.unlink()
    
    settings.DATABASE_URL = "sqlite:///./test_diagnose.db"
    
    # Monkey-patch the engine to use the test DB
    import db as db_module
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    test_engine = create_engine("sqlite:///./test_diagnose.db", connect_args={"check_same_thread": False})
    db_module.engine = test_engine
    db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db_module.Base.metadata.create_all(bind=test_engine)
    
    # Step 1: Direct OCR tests on synthetic documents
    log("\n" + "=" * 60)
    log("PHASE 1: Direct OCR tests on synthetic documents")
    log("=" * 60)
    
    for pan_dir_name in ["UJALK5542W", "HAOEL7625O"]:
        pan_dir = DOCS_DIR / pan_dir_name
        if not pan_dir.exists():
            log(f"Directory not found: {pan_dir}")
            continue
        
        log(f"\n--- Testing documents from {pan_dir_name} ---")
        for doc_type in ["PAN", "GST", "BANK_PROOF"]:
            file_path = pan_dir / f"{doc_type}.png"
            if file_path.exists():
                result = test_direct_ocr(doc_type, file_path)
                if result:
                    fields, confidence, raw_text = result
                    test_format_check(raw_text, doc_type)
            else:
                log(f"  File not found: {file_path}")
    
    # Step 2: Full upload flow (like the user's scenario)
    log("\n" + "=" * 60)
    log("PHASE 2: Full upload flow (signup + upload + check)")
    log("=" * 60)
    
    # Create test accounts
    db = db_module.SessionLocal()
    try:
        for m in TEST_MERCHANTS:
            existing = db.query(Merchant).filter(Merchant.email == m["email"]).first()
            if not existing:
                merchant = Merchant(
                    business_name=m["name"],
                    email=m["email"],
                    password_hash=hash_password(m["password"]),
                    role="merchant",
                    onboarding_status="pending",
                )
                db.add(merchant)
        db.commit()
        log("Test accounts created")
    finally:
        db.close()
    
    # Test upload flow for each merchant
    for m in TEST_MERCHANTS:
        pan_dir = DOCS_DIR / m["pan"]
        if pan_dir.exists():
            test_full_upload_flow(m["email"], m["password"], pan_dir)
    
    # Step 3: Test with the SAME account twice (to reproduce the user's scenario)
    log("\n" + "=" * 60)
    log("PHASE 3: Same account, second upload attempt (user's scenario)")
    log("=" * 60)
    
    m = TEST_MERCHANTS[0]
    pan_dir = DOCS_DIR / m["pan"]
    if pan_dir.exists():
        # First, check current status
        import requests
        API = "http://localhost:8000"
        r = requests.post(f"{API}/auth/login", json={"email": m["email"], "password": m["password"]})
        if r.status_code == 200:
            token = r.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            
            r = requests.get(f"{API}/documents/merchant-status", headers=headers)
            if r.status_code == 200:
                status = r.json()
                log(f"Current status: {status['onboarding_status']}")
                log(f"Documents: {len(status['documents'])}")
                
                # If already submitted, we can't upload again (by design)
                if status["onboarding_status"] == "submitted":
                    log("Merchant already submitted - cannot re-upload (this is expected)")
                    log("To test re-upload, use a fresh account or restart application")
                else:
                    log("Merchant not yet submitted - testing re-upload...")
                    test_full_upload_flow(m["email"], m["password"], pan_dir)
    
    # Summary
    log("\n" + "=" * 60)
    log("SUMMARY")
    log("=" * 60)
    passed = sum(1 for r in RESULTS if r["passed"])
    failed = sum(1 for r in RESULTS if not r["passed"])
    total = len(RESULTS)
    log(f"Total: {total} | Passed: {passed} | Failed: {failed} | Rate: {(passed/total*100) if total else 0:.1f}%")
    
    for r in RESULTS:
        log(f"  {'✅' if r['passed'] else '❌'} {r['name']}: {r['detail']}")
    
    # Cleanup
    if db_path.exists():
        db_path.unlink()
        log("\nTest database cleaned up")


if __name__ == "__main__":
    main()
