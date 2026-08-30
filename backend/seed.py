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
    Creates synthetic merchant accounts pre-tagged with an expected
    outcome, so /admin/batch-test can measure real accuracy. These
    accounts don't have uploaded documents by default — they exist so
    the batch-test scoring logic and reviewer views have data to show
    even before a live demo upload happens.
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
        )
        db.add(merchant)
        db.flush()
        db.add(AuditLog(merchant_id=merchant.id, action="expected_outcome", reason="flagged"))

    db.commit()


def main() -> None:
    """Seed the database — but only if it's empty (idempotent)."""
    init_db()
    db = SessionLocal()
    try:
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
