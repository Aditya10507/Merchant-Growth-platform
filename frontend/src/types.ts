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
  | "temporarily_unavailable"
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

/** Result of an admin maintenance action (archiving E2E/test merchants). */
export interface MaintenanceResult {
  archived_count: number;
  archived_emails: string[];
  remaining_count: number;
}

// ---------------------------------------------------------------------------
// Feature 1: failure-injection (chaos panel) — mirrors FaultStateResponse
// ---------------------------------------------------------------------------

/** A named demo outage the admin can toggle on/off. */
export type FaultName = "ocr_down" | "llm_down" | "sources_down";

export interface FaultState {
  ocr_down: boolean;
  llm_down: boolean;
  sources_down: boolean;
  active: string[];
}

// ---------------------------------------------------------------------------
// Feature 2: empirical risk calibration — mirrors RiskEvalReportResponse
// ---------------------------------------------------------------------------

export interface ClassScoreStats {
  count: number;
  mean_score: number;
  min_score: number;
  max_score: number;
}

export interface ThresholdRow {
  threshold: number;
  precision: number;
  recall: number;
  f1: number;
  accuracy: number;
  true_positives: number;
  false_positives: number;
  false_negatives: number;
  true_negatives: number;
}

export interface RiskEvalReport {
  total_labeled: number;
  good_count: number;
  bad_count: number;
  replayed_count: number;
  pipeline_scored_count: number;
  good_stats: ClassScoreStats;
  bad_stats: ClassScoreStats;
  best_threshold: number;
  best_f1: number;
  best_confusion: { [key: string]: number };
  threshold_sweep: ThresholdRow[];
  weights_used: { [key: string]: number };
}

// ---------------------------------------------------------------------------
// Feature 4: live system health — mirrors SystemHealthResponse
// ---------------------------------------------------------------------------

export interface HealthBucket {
  count: number;
  succeeded: number;
  failed: number;
  success_rate: number | null;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
}

export interface RequestHealth {
  total: number;
  errors_5xx: number;
  error_rate: number | null;
  avg_latency_ms: number | null;
}

export interface SystemHealth {
  uptime_seconds: number;
  window_seconds: number;
  ocr: HealthBucket;
  llm: HealthBucket;
  requests: RequestHealth;
  active_faults: string[];
}

export interface ApiErrorBody {
  detail: string;
}
