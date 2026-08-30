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
    "inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60";
  const variants: Record<NonNullable<ButtonProps["variant"]>, string> = {
    primary: "bg-gray-900 text-white hover:bg-black focus-visible:ring-gray-900",
    secondary: "bg-white text-gray-900 border border-gray-300 hover:bg-gray-50 focus-visible:ring-gray-900",
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

export const Button = memo(ButtonBase);
