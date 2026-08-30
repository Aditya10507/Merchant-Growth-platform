-- Auto-generated from backend/db.py SQLAlchemy models.
-- This is the authoritative database schema for the project.
-- Dialect shown: SQLite (the MVP default). Swap DATABASE_URL in .env for Postgres;
-- SQLAlchemy adapts types automatically when you do -- this file is for reference only.
--
-- TABLE RELATIONSHIPS
-- merchants (1) --< documents (many)      via documents.merchant_id
-- merchants (1) --< audit_logs (many)     via audit_logs.merchant_id
-- documents (1) --< audit_logs (many)     via audit_logs.document_id (nullable)
--
-- The 5 tables below are the simulated external verification sources
-- (government DB, CKYC, automated checks, bank validation, compliance
-- review). They are looked up by pan_number/account_number at
-- verification time -- they do not have foreign keys to merchants
-- because in a real system they would be external, independent data
-- sources, not owned by this application schema.
--   govt_database, ckyc_records, automated_verification,
--   bank_account_validation, compliance_reviews


CREATE TABLE automated_verification (
	id INTEGER NOT NULL, 
	pan_number VARCHAR(20) NOT NULL, 
	check_type VARCHAR(50) NOT NULL, 
	result VARCHAR(20) NOT NULL, 
	confidence FLOAT NOT NULL, 
	PRIMARY KEY (id)
)

;
CREATE INDEX ix_automated_verification_pan_number ON automated_verification (pan_number);


CREATE TABLE bank_account_validation (
	id INTEGER NOT NULL, 
	account_number VARCHAR(30) NOT NULL, 
	ifsc VARCHAR(15) NOT NULL, 
	name_match_score FLOAT NOT NULL, 
	verified VARCHAR(10) NOT NULL, 
	PRIMARY KEY (id)
)

;
CREATE UNIQUE INDEX ix_bank_account_validation_account_number ON bank_account_validation (account_number);


CREATE TABLE ckyc_records (
	id INTEGER NOT NULL, 
	ckyc_id VARCHAR(50) NOT NULL, 
	pan_number VARCHAR(20) NOT NULL, 
	kyc_status VARCHAR(20) NOT NULL, 
	last_updated VARCHAR(30) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (ckyc_id)
)

;
CREATE INDEX ix_ckyc_records_pan_number ON ckyc_records (pan_number);


CREATE TABLE compliance_reviews (
	id INTEGER NOT NULL, 
	pan_number VARCHAR(20) NOT NULL, 
	flag_reason VARCHAR(255), 
	reviewer VARCHAR(100), 
	status VARCHAR(20) NOT NULL, 
	PRIMARY KEY (id)
)

;
CREATE INDEX ix_compliance_reviews_pan_number ON compliance_reviews (pan_number);


CREATE TABLE govt_database (
	id INTEGER NOT NULL, 
	pan_number VARCHAR(20) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	dob VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	PRIMARY KEY (id)
)

;
CREATE UNIQUE INDEX ix_govt_database_pan_number ON govt_database (pan_number);


CREATE TABLE merchants (
	id INTEGER NOT NULL, 
	business_name VARCHAR(255) NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	onboarding_status VARCHAR(30) NOT NULL, 
	rejection_reason TEXT, 
	matched_checks TEXT, 
	mismatched_checks TEXT, 
	rejection_cause TEXT, 
	created_at DATETIME, 
	PRIMARY KEY (id)
)

;
CREATE UNIQUE INDEX ix_merchants_email ON merchants (email);


CREATE TABLE documents (
	id INTEGER NOT NULL, 
	merchant_id INTEGER NOT NULL, 
	doc_type VARCHAR(20) NOT NULL, 
	file_path VARCHAR(500) NOT NULL, 
	extracted_fields_json TEXT, 
	ocr_confidence FLOAT, 
	verification_status VARCHAR(30) NOT NULL, 
	rejection_reason TEXT, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(merchant_id) REFERENCES merchants (id)
)

;


CREATE TABLE audit_logs (
	id INTEGER NOT NULL, 
	merchant_id INTEGER NOT NULL, 
	document_id INTEGER, 
	action VARCHAR(50) NOT NULL, 
	reason TEXT NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(merchant_id) REFERENCES merchants (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id)
)

;

