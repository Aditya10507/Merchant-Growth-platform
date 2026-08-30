/**
 * RiskBadge.tsx
 * -------------
 * Monochrome pill showing a merchant's risk score. Fill intensity and
 * icon distinguish risk levels — never hue.
 */
import { memo } from "react";
import { CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import { getRiskLevel } from "../constants";

interface LevelStyle {
  classes: string;
  icon: typeof CheckCircle2 | null;
}

const LEVEL_STYLES: Record<ReturnType<typeof getRiskLevel>, LevelStyle> = {
  unscored: { classes: "bg-white border border-gray-300 text-gray-500", icon: null },
  low: { classes: "bg-gray-900 text-white", icon: CheckCircle2 },
  medium: { classes: "bg-white border-2 border-gray-800 text-gray-900", icon: AlertTriangle },
  high: { classes: "bg-gray-900 text-white", icon: XCircle },
};

const LEVEL_LABELS: Record<ReturnType<typeof getRiskLevel>, string> = {
  unscored: "Not yet scored",
  low: "Low risk",
  medium: "Medium risk",
  high: "High risk",
};

function RiskBadgeBase({ score }: { score: number | null }) {
  const level = getRiskLevel(score);
  const style = LEVEL_STYLES[level];
  const Icon = style.icon;
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium ${style.classes}`}>
      {Icon && <Icon className="h-3.5 w-3.5" />}
      {score !== null && <span className="font-semibold">{score}</span>}
      {LEVEL_LABELS[level]}
    </span>
  );
}

export const RiskBadge = memo(RiskBadgeBase);
