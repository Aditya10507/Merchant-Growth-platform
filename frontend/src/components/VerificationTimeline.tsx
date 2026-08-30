/**
 * VerificationTimeline.tsx
 * -----------------------
 * A shared, reusable audit-trail visualization component.
 *
 * Used in two contexts:
 *   1. AdminPanel's merchant detail view — shows full technical reason text.
 *   2. Optionally in DashboardPage — in that case, only action labels and
 *      timestamps are shown (no raw technical reasons leaked to merchants).
 *
 * Renders a vertical timeline with one row per AuditLogEntry, each showing
 * the action label, reason text, and formatted timestamp.
 */

import { memo } from "react";

import { ACTION_LABELS } from "../constants";
import type { AuditLogEntry } from "../types";

interface VerificationTimelineProps {
  entries: AuditLogEntry[];
  /** When true, omits the reason text — used for the merchant-facing view. */
  compact?: boolean;
}

/**
 * Formats an ISO timestamp into a human-readable date-time string.
 * Uses toLocaleString for locale-aware formatting without external dependencies.
 */
function formatTimestamp(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function VerificationTimelineBase({ entries, compact = false }: VerificationTimelineProps) {
  if (entries.length === 0) {
    return (
      <p className="text-sm text-gray-500 italic" role="status">
        No audit entries yet.
      </p>
    );
  }

  return (
    <ol aria-label="Verification timeline" className="relative ml-3 border-l border-gray-200">
      {entries.map((entry, index) => (
        <li key={`${entry.action}-${entry.created_at}-${index}`} className="mb-6 ml-6">
          {/* Timeline dot — color varies by action type */}
          <span
            className={`absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full border-2 border-white ${
              entry.action === "approved"
                ? "bg-green-500"
                : entry.action === "rejected"
                  ? "bg-red-500"
                  : entry.action === "flagged" || entry.action === "manual_review_resolution"
                    ? "bg-amber-500"
                    : "bg-gray-400"
            }`}
            aria-hidden="true"
          />

          {/* Action label — use ACTION_LABELS constant, fall back to raw action string */}
          <h4 className="text-sm font-medium text-gray-900">
            {ACTION_LABELS[entry.action] ?? entry.action}
          </h4>

          {/* Reason text — only shown in non-compact (admin) mode */}
          {!compact && entry.reason && (
            <p className="mt-1 text-xs text-gray-600">{entry.reason}</p>
          )}

          {/* Timestamp */}
          <time
            dateTime={entry.created_at}
            className="mt-0.5 block text-xs text-gray-400"
          >
            {formatTimestamp(entry.created_at)}
          </time>
        </li>
      ))}
    </ol>
  );
}

export const VerificationTimeline = memo(VerificationTimelineBase);
