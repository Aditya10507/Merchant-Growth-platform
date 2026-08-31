/**
 * StatusBadge.tsx
 * ---------------
 * Shows a document/merchant's verification status as a monochrome
 * badge with icon + text label. Fill intensity and icon distinguish
 * status levels — never hue.
 */

import { memo } from "react";
import { Clock, AlertTriangle, XCircle, CheckCircle2 } from "lucide-react";

import { STATUS_LABELS } from "../constants";
import type { VerificationStatus } from "../types";

interface StatusStyle {
  classes: string;
  icon: typeof Clock | null;
}

const STATUS_STYLES: Record<VerificationStatus, StatusStyle> = {
  uploaded: { classes: "bg-white border border-gray-300 text-gray-700", icon: null },
  verifying: { classes: "bg-gray-100 border border-gray-300 text-gray-800", icon: Clock },
  invalid_format: { classes: "bg-white border-2 border-gray-800 text-gray-900", icon: AlertTriangle },
  pending: { classes: "bg-gray-100 border border-gray-300 text-gray-800", icon: Clock },
  submitted: { classes: "bg-gray-100 border border-gray-300 text-gray-800", icon: Clock },
  verified_matching: { classes: "bg-gray-100 border border-gray-300 text-gray-800", icon: Clock },
  verified_mismatched: { classes: "bg-white border-2 border-gray-800 text-gray-900", icon: AlertTriangle },
  approved: { classes: "bg-gray-900 text-white", icon: CheckCircle2 },
  active: { classes: "bg-gray-900 text-white", icon: CheckCircle2 },
  flagged: { classes: "bg-white border-2 border-gray-800 text-gray-900", icon: AlertTriangle },
  rejected: { classes: "bg-gray-900 text-white", icon: XCircle },
};

function StatusBadgeBase({ status }: { status: VerificationStatus }) {
  const style = STATUS_STYLES[status];
  const Icon = style.icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium ${style.classes}`}
    >
      {Icon && <Icon className="h-3.5 w-3.5" />}
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

export const StatusBadge = memo(StatusBadgeBase);
