/**
 * Button.tsx
 * ----------
 * A single reusable button used everywhere in the app, so styling and
 * disabled/loading behavior stay consistent instead of being
 * reimplemented per screen.
 */

import { memo, type ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
  isLoading?: boolean;
}

function ButtonBase({
  variant = "primary",
  isLoading = false,
  disabled,
  children,
  className = "",
  ...rest
}: ButtonProps) {
  const base =
    "inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60";
  const variants: Record<NonNullable<ButtonProps["variant"]>, string> = {
    primary: "bg-brand-600 text-white hover:bg-brand-700 focus-visible:ring-brand-600",
    secondary: "bg-white text-brand-700 border border-brand-600 hover:bg-brand-50 focus-visible:ring-brand-600",
  };

  return (
    <button
      className={`${base} ${variants[variant]} ${className}`}
      disabled={disabled || isLoading}
      aria-busy={isLoading}
      {...rest}
    >
      {isLoading ? "Please wait…" : children}
    </button>
  );
}

// memo() prevents this component from re-rendering when parent state
// changes but this button's own props haven't — relevant here since
// forms re-render on every keystroke.
export const Button = memo(ButtonBase);
