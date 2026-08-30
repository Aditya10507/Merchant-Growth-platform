/**
 * StatusBadge.tsx
 * ---------------
 * Shows a document/merchant's verification status as a color-coded
 * pill. Color is never the only signal — the text label is always
 * present too, per the accessibility requirement that status must not
 * rely on color alone.
 */

import { memo } from "react";

import { STATUS_LABELS } from "../constants";
import type { VerificationStatus } from "../types";

const STATUS_STYLES: Record<VerificationStatus, string> = {
  uploaded: "bg-gray-100 text-gray-700",
  verifying: "bg-blue-100 text-blue-700",
  invalid_format: "bg-red-100 text-red-800",
  submitted: "bg-indigo-100 text-indigo-800",
  verified_matching: "bg-green-100 text-green-800",
  verified_mismatched: "bg-amber-100 text-amber-800",
  approved: "bg-green-100 text-green-800",
  flagged: "bg-amber-100 text-amber-800",
  rejected: "bg-red-100 text-red-800",
};

function StatusBadgeBase({ status }: { status: VerificationStatus }) {
  return (
    <span
      className={`inline-block rounded-full px-3 py-1 text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

export const StatusBadge = memo(StatusBadgeBase);
