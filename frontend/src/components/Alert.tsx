/**
 * Alert.tsx
 * ---------
 * A single reusable banner for error/success/info messages. Distinguished
 * by icon and border weight, never by color hue (see FEATURE_3 design tokens).
 */
import { memo, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info } from "lucide-react";

interface AlertProps {
  variant: "error" | "success" | "info";
  children: ReactNode;
}

const VARIANT_CONFIG: Record<AlertProps["variant"], { border: string; Icon: typeof Info }> = {
  error: { border: "border-l-4 border-gray-900", Icon: AlertTriangle },
  success: { border: "border-l-4 border-gray-400", Icon: CheckCircle2 },
  info: { border: "border-l-4 border-gray-300", Icon: Info },
};

function AlertBase({ variant, children }: AlertProps) {
  const { border, Icon } = VARIANT_CONFIG[variant];
  return (
    <div
      role={variant === "error" ? "alert" : "status"}
      className={`flex items-start gap-2 bg-white ${border} px-4 py-3 text-sm text-gray-800`}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-gray-700" />
      <span>{children}</span>
    </div>
  );
}

export const Alert = memo(AlertBase);
