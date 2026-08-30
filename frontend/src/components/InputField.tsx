/**
 * InputField.tsx
 * --------------
 * A labeled input with an associated error message. Always renders a
 * visible <label> (not a placeholder-only field) and wires up
 * aria-describedby/aria-invalid for screen readers, per the
 * accessibility requirements in the UI/UX doc.
 */

import { memo, useId, type InputHTMLAttributes } from "react";

interface InputFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

function InputFieldBase({ label, error, className = "", ...rest }: InputFieldProps) {
  const inputId = useId();
  const errorId = `${inputId}-error`;

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={inputId} className="text-sm font-medium text-gray-700">
        {label}
      </label>
      <input
        id={inputId}
        className={`rounded-md border px-3 py-2 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 ${
          error ? "border-red-500" : "border-gray-300"
        } ${className}`}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : undefined}
        {...rest}
      />
      {error && (
        <p id={errorId} className="text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export const InputField = memo(InputFieldBase);
