/**
 * RiskBreakdown.tsx
 * -----------------
 * Point-by-point explanation of a merchant's risk score: each mismatched
 * check shown with the points it contributed. This is the "why this score?"
 * answer for the admin.
 *
 * RISK_WEIGHTS mirrors backend/config.py's RISK_WEIGHTS — keep in sync.
 */
import { memo } from "react";
import { AlertTriangle } from "lucide-react";
import type { CheckResult } from "../types";

// Mirrors backend/config.py's RISK_WEIGHTS
const RISK_WEIGHTS: Record<string, number> = {
  govt_database: 30,
  ckyc_records: 20,
  automated_verification: 20,
  bank_account_validation: 20,
  compliance_reviews: 10,
  llm_cross_check: 15,
  fraud_ring_pan: 40,
  fraud_ring_bank: 40,
};

function weightFor(checkName: string): number {
  const key = checkName.startsWith("llm_cross_check") ? "llm_cross_check" : checkName;
  return RISK_WEIGHTS[key] ?? 10;
}

function isFraudRingCheck(checkName: string): boolean {
  return checkName.startsWith("fraud_ring_");
}

function RiskBreakdownBase({ mismatchedChecks }: { mismatchedChecks: CheckResult[] }) {
  if (mismatchedChecks.length === 0) {
    return <p className="text-sm text-gray-600">No risk-contributing checks found.</p>;
  }
  return (
    <ul className="flex flex-col gap-2">
      {mismatchedChecks.map((check, i) => (
        <li
          key={i}
          className={`flex items-start justify-between gap-3 rounded-md px-3 py-2 text-sm ${
            isFraudRingCheck(check.check_name)
              ? "border-2 border-gray-900 bg-gray-100"
              : "bg-gray-50 border border-gray-200"
          }`}
        >
          <span className={isFraudRingCheck(check.check_name) ? "font-semibold text-gray-900 flex items-center gap-1" : "text-gray-700"}>
            {isFraudRingCheck(check.check_name) && <AlertTriangle className="h-3.5 w-3.5 shrink-0" />}
            {check.detail}
          </span>
          <span className="shrink-0 font-semibold text-gray-900">+{weightFor(check.check_name)}</span>
        </li>
      ))}
    </ul>
  );
}

export const RiskBreakdown = memo(RiskBreakdownBase);
