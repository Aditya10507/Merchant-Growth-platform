"""
seed.py
-------
Populates the database with:
  1. Synthetic entries in the 5 "external" verification tables — a mix
     of clean, verifiable records and deliberate mismatches/gaps, so the
     Decision Engine has real cases to exercise.
  2. A reviewer and an admin test account.
  3. Ground-truth `expected_outcome` audit-log entries used by the
     /admin/batch-test report to measure accuracy against known answers.

Run with:
    python seed.py

Idempotent: if the database already contains merchant data, seeding is
skipped so live user accounts and uploaded documents are never wiped.
"""

from auth import hash_password
from db import (
    AuditLog,
    AutomatedVerification,
    BankAccountValidation,
    CkycRecord,
    ComplianceReview,
    GovtDatabase,
    Merchant,
    SessionLocal,
    apply_migrations,
    init_db,
)

# Synthetic PAN numbers used across the seed data. None of these belong
# to real people or businesses — they follow the correct format only.
CLEAN_PAN_NUMBERS = [f"AAAAA{1000 + i}A" for i in range(20)]
MISMATCH_PAN_NUMBERS = [f"BBBBB{2000 + i}B" for i in range(10)]


def seed_external_sources(db) -> None:
    for i, pan in enumerate(CLEAN_PAN_NUMBERS):
        db.add(GovtDatabase(pan_number=pan, name=f"Test Merchant {i}", dob="1990-01-01", status="verified"))
        db.add(CkycRecord(ckyc_id=f"CKYC{i}", pan_number=pan, kyc_status="verified", last_updated="2026-01-01"))
        db.add(AutomatedVerification(pan_number=pan, check_type="identity_match", result="pass", confidence=0.97))
        db.add(BankAccountValidation(account_number=f"1000000000{i}", ifsc="HDFC0001234", name_match_score=95.0, verified="yes"))

    for i, pan in enumerate(MISMATCH_PAN_NUMBERS):
        # Deliberately incomplete/failing records to exercise the FLAGGED path.
        db.add(GovtDatabase(pan_number=pan, name=f"Mismatch Merchant {i}", dob="1985-05-05", status="invalid"))
        db.add(AutomatedVerification(pan_number=pan, check_type="identity_match", result="fail", confidence=0.40))
        if i % 2 == 0:
            db.add(ComplianceReview(pan_number=pan, flag_reason="Suspicious registration pattern", reviewer="system", status="flagged"))

    db.commit()


def seed_accounts(db) -> None:
    if not db.query(Merchant).filter(Merchant.email == "reviewer@example.com").first():
        db.add(Merchant(
            business_name="Compliance Reviewer",
            email="reviewer@example.com",
            password_hash=hash_password("ReviewerPass123"),
            role="reviewer",
            onboarding_status="n/a",
        ))
    if not db.query(Merchant).filter(Merchant.email == "admin@example.com").first():
        db.add(Merchant(
            business_name="Platform Admin",
            email="admin@example.com",
            password_hash=hash_password("AdminPass123"),
            role="admin",
            onboarding_status="n/a",
        ))
    db.commit()


def seed_test_merchants(db) -> None:
    """
    Creates synthetic ground-truth merchant accounts pre-tagged with an
    expected outcome, so /admin/batch-test and /admin/risk-eval can
    measure real accuracy against known answers.

    These accounts are created ARCHIVED (is_test=True, Session 24): they
    exist purely as the labeled scoring set — the admin review queue must
    show only real applicants, never demo rows. The accuracy reports
    score the labeled set by its `expected_outcome` audit entries
    regardless of the is_test flag (see admin.py run_batch_test and
    risk_eval.build_labeled_cases).
    """
    for i, pan in enumerate(CLEAN_PAN_NUMBERS[:15]):
        email = f"clean_merchant_{i}@example.com"
        if db.query(Merchant).filter(Merchant.email == email).first():
            continue
        merchant = Merchant(
            business_name=f"Clean Test Business {i}",
            email=email,
            password_hash=hash_password("TestPass123"),
            role="merchant",
            onboarding_status="active",
            is_test=True,
        )
        db.add(merchant)
        db.flush()
        db.add(AuditLog(merchant_id=merchant.id, action="expected_outcome", reason="approved"))

    for i, pan in enumerate(MISMATCH_PAN_NUMBERS):
        email = f"mismatch_merchant_{i}@example.com"
        if db.query(Merchant).filter(Merchant.email == email).first():
            continue
        merchant = Merchant(
            business_name=f"Mismatch Test Business {i}",
            email=email,
            password_hash=hash_password("TestPass123"),
            role="merchant",
            onboarding_status="flagged",
            is_test=True,
        )
        db.add(merchant)
        db.flush()
        db.add(AuditLog(merchant_id=merchant.id, action="expected_outcome", reason="flagged"))

    db.commit()


# Test document PAN numbers used in the E2E test suite and demo.
# These MUST exist in the external verification tables for admin
# verification to find matching records. This function is idempotent
# and runs on every startup, even if the database was already seeded.
TEST_DOC_PANS = {
    "clean": [
        {"pan": "UJALK5542W", "name": "Baljit Khan", "gst": "27UJALK5542W1Z5", "ifsc": "BARB0071834", "account": "267390881362"},
        {"pan": "HAOEL7625O", "name": "Meera Kamath", "gst": "27HAOEL7625O1Z5", "ifsc": "IDIB0252597", "account": "4233817042012"},
        {"pan": "CCZEE2615Q", "name": "Meera Mukherjee", "gst": "27CCZEE2615Q1Z5", "ifsc": "ICIC0912352", "account": "523353074112178"},
    ],
    "mismatch": [
        {"pan": "VDAWP9860F", "name": "Manpreet Patel", "gst": "27VDAWP9860F1Z5", "ifsc": "CNRB0894787", "account": "1279011420945917"},
        {"pan": "RFBPO7258K", "name": "Prakash Hegde", "gst": "27RFBPO7258K1Z5", "ifsc": "BARB0999285", "account": "301376505202"},
    ],
}


def ensure_test_doc_pan_records(db) -> None:
    """Ensure external verification tables have records for test document PANs.

    This runs on every startup (idempotent) so that even if the main seed
    was skipped (database already populated), the test document PANs are
    present in the external verification tables. Without this, admin
    verification would find no matching records and reject all merchants.
    """
    added = 0
    for group, docs in TEST_DOC_PANS.items():
        for doc in docs:
            pan = doc["pan"]
            # Govt database
            if not db.query(GovtDatabase).filter(GovtDatabase.pan_number == pan).first():
                db.add(GovtDatabase(
                    pan_number=pan, name=doc["name"], dob="1990-01-01",
                    status="verified" if group == "clean" else "invalid",
                ))
                added += 1
            # CKYC
            if not db.query(CkycRecord).filter(CkycRecord.pan_number == pan).first():
                db.add(CkycRecord(
                    ckyc_id=f"CKYC_{pan}", pan_number=pan,
                    kyc_status="verified" if group == "clean" else "rejected",
                    last_updated="2026-01-01",
                ))
                added += 1
            # Automated verification
            if not db.query(AutomatedVerification).filter(AutomatedVerification.pan_number == pan).first():
                db.add(AutomatedVerification(
                    pan_number=pan, check_type="identity_match",
                    result="pass" if group == "clean" else "fail",
                    confidence=0.97 if group == "clean" else 0.40,
                ))
                added += 1
            # Bank account validation
            if not db.query(BankAccountValidation).filter(BankAccountValidation.account_number == doc["account"]).first():
                db.add(BankAccountValidation(
                    account_number=doc["account"], ifsc=doc["ifsc"],
                    name_match_score=95.0 if group == "clean" else 30.0,
                    verified="yes" if group == "clean" else "no",
                ))
                added += 1
            # Compliance review (only for clean PANs)
            if group == "clean" and not db.query(ComplianceReview).filter(ComplianceReview.pan_number == pan).first():
                db.add(ComplianceReview(
                    pan_number=pan, flag_reason=None,
                    reviewer="system", status="clear",
                ))
                added += 1
    if added > 0:
        db.commit()
        print(f"Ensured {added} test document PAN records in external verification tables.")


def main() -> None:
    """Seed the database — but only if it's empty (idempotent)."""
    init_db()
    # CRITICAL: this module runs standalone (`python seed.py`) as the
    # Docker/Render start command BEFORE uvicorn boots. The ORM queries
    # below need the latest schema, so apply Alembic migrations here too
    # (idempotent; stamps at head on a fresh DB).
    # Note: init_db() already self-heals the schema via
    # _ensure_is_test_column(), so even if Alembic fails here the deploy
    # can proceed — the failure is printed to the log but is not fatal.
    apply_migrations()
    db = SessionLocal()
    try:
        # ALWAYS ensure test document PANs exist in external tables.
        # This is idempotent and safe to run on every startup.
        ensure_test_doc_pan_records(db)

        # Check if seed data already exists — skip if the database was
        # previously seeded so we never overwrite live user data.
        existing_merchants = db.query(Merchant).count()
        if existing_merchants > 0:
            print(
                f"Database already contains {existing_merchants} merchant(s). "
                "Skipping seed — data preserved."
            )
            return

        # Database is empty — run all seed functions
        seed_external_sources(db)
        seed_accounts(db)
        seed_test_merchants(db)
        print(
            "Seed complete: external verification tables, reviewer/admin "
            "accounts, and 25 test merchants created."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
