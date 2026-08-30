/**
 * Alert.tsx
 * ---------
 * A single reusable banner for error/success/info messages, used for
 * both client-side validation feedback and backend error responses.
 */

import { memo, type ReactNode } from "react";

interface AlertProps {
  variant: "error" | "success" | "info";
  children: ReactNode;
}

const VARIANT_STYLES: Record<AlertProps["variant"], string> = {
  error: "bg-red-50 text-red-800 border-red-200",
  success: "bg-green-50 text-green-800 border-green-200",
  info: "bg-blue-50 text-blue-800 border-blue-200",
};

function AlertBase({ variant, children }: AlertProps) {
  return (
    <div
      role={variant === "error" ? "alert" : "status"}
      className={`rounded-md border px-4 py-3 text-sm ${VARIANT_STYLES[variant]}`}
    >
      {children}
    </div>
  );
}

export const Alert = memo(AlertBase);
