/**
 * types.ts
 * --------
 * Every shape of data the frontend sends or receives lives here.
 * Keeping types centralized avoids duplication and guarantees the
 * frontend and backend response contracts stay in sync in one place.
 */

export type DocumentType = "PAN" | "GST" | "BANK_PROOF";

export type VerificationStatus =
  | "uploaded"
  | "verifying"
  | "invalid_format"
  | "pending"
  | "submitted"
  | "verified_matching"
  | "verified_mismatched"
  | "approved"
  | "active"
  | "flagged"
  | "rejected";

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  merchant_id: number;
  business_name: string;
  role: "merchant" | "reviewer" | "admin";
}

export interface DocumentStatus {
  id: number;
  doc_type: DocumentType;
  verification_status: VerificationStatus;
  ocr_confidence: number | null;
  extracted_fields: Record<string, string> | null;
  rejection_reason: string | null;
}

export interface MerchantStatus {
  merchant_id: number;
  onboarding_status: string;
  rejection_reason: string | null;
  documents: DocumentStatus[];
}

/**
 * A discriminated union representing every possible state of an async
 * operation. Using this consistently avoids ad-hoc boolean flags like
 * `isLoading` + `isError` that can contradict each other.
 */
export type AsyncState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; message: string };

/**
 * Admin panel types — mirrors the backend's Pydantic schemas
 * for the reviewer/admin merchant-management endpoints.
 */
export interface MerchantSummary {
  merchant_id: number;
  business_name: string;
  email: string;
  onboarding_status: string;
  risk_score: number | null;
  created_at: string;
}

export interface AuditLogEntry {
  action: string;
  reason: string;
  document_id: number | null;
  created_at: string;
}

export interface MerchantDetail {
  merchant_id: number;
  business_name: string;
  email: string;
  onboarding_status: string;
  rejection_reason: string | null;
  matched_checks: CheckResult[] | null;
  mismatched_checks: CheckResult[] | null;
  rejection_cause: string | null;
  risk_score: number | null;
  documents: DocumentStatus[];
  audit_trail: AuditLogEntry[];
}

/** Phase 3: one check outcome from the structured verification breakdown. */
export interface CheckResult {
  check_name: string;
  document_type: string;
  matched: boolean;
  detail: string;
}

export interface ApiErrorBody {
  detail: string;
}
