/**
 * RiskBadge.tsx
 * -------------
 * Colored pill showing a merchant's risk score. Color is never the only
 * signal — the numeric score and a text label are always shown too.
 */
import { memo } from "react";
import { getRiskLevel } from "../constants";

const LEVEL_STYLES: Record<ReturnType<typeof getRiskLevel>, string> = {
  unscored: "bg-gray-100 text-gray-500",
  low: "bg-green-100 text-green-800",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-red-100 text-red-800",
};

const LEVEL_LABELS: Record<ReturnType<typeof getRiskLevel>, string> = {
  unscored: "Not yet scored",
  low: "Low risk",
  medium: "Medium risk",
  high: "High risk",
};

function RiskBadgeBase({ score }: { score: number | null }) {
  const level = getRiskLevel(score);
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium ${LEVEL_STYLES[level]}`}>
      {score !== null && <span className="font-semibold">{score}</span>}
      {LEVEL_LABELS[level]}
    </span>
  );
}

export const RiskBadge = memo(RiskBadgeBase);
