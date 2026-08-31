/**
 * constants.ts
 * ------------
 * Centralized configuration so no component hardcodes a URL, limit, or
 * label directly. Change a value once here instead of hunting through
 * component files.
 */

import type { DocumentType } from "./types";

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024; // 5 MB, mirrors backend limit

/** Human-readable version of the max upload size for display in the UI. */
export const MAX_UPLOAD_SIZE_MB = MAX_UPLOAD_SIZE_BYTES / (1024 * 1024);

export const ALLOWED_FILE_TYPES = ["image/jpeg", "image/png", "application/pdf"] as const;

/** Human-readable list of allowed file types for display in the UI. */
export const ALLOWED_FILE_TYPES_LABEL = "JPG, PNG, or PDF";

export const DOCUMENT_SLOTS: ReadonlyArray<{ type: DocumentType; label: string; hint: string }> = [
  { type: "PAN", label: "PAN card", hint: "Upload a clear photo or scan of your PAN card" },
  { type: "GST", label: "GST certificate", hint: "Upload your GST registration certificate" },
  { type: "BANK_PROOF", label: "Bank proof", hint: "Upload a cancelled cheque or bank statement" },
];

export const PASSWORD_MIN_LENGTH = 8;

export const STATUS_LABELS: Record<string, string> = {
  uploaded: "Uploaded",
  verifying: "Verifying",
  invalid_format: "Invalid document",
  pending: "Pending",
  submitted: "Awaiting verification",
  verified_matching: "Verified - matches",
  verified_mismatched: "Verified - mismatch found",
  approved: "Approved",
  active: "Active",
  flagged: "Needs review",
  rejected: "Rejected",
};

/** Maps audit-log action strings to human-readable labels for the timeline. */
export const ACTION_LABELS: Record<string, string> = {
  approved: "Approved",
  flagged: "Flagged for review",
  rejected: "Rejected",
  submitted: "Submitted for review",
  verification_run: "Verification run",
  system_recommendation: "Automated recommendation",
  application_restarted: "Application restarted",
  manual_review_resolution: "Reviewer decision",
  expected_outcome: "Expected outcome",
};

// --- Risk scoring (Feature 1) ---
export const RISK_LEVEL_THRESHOLDS = { LOW: 30, MEDIUM: 60 } as const;

export function getRiskLevel(score: number | null): "unscored" | "low" | "medium" | "high" {
  if (score === null) return "unscored";
  if (score < RISK_LEVEL_THRESHOLDS.LOW) return "low";
  if (score < RISK_LEVEL_THRESHOLDS.MEDIUM) return "medium";
  return "high";
}
